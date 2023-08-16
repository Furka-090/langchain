from typing import Any, Dict, List, Mapping, Optional

from pydantic import model_validator, ConfigDict

from langchain.callbacks.manager import CallbackManagerForLLMRun
from langchain.llms.base import LLM
from langchain.llms.utils import enforce_stop_tokens
from langchain.utils import get_from_dict_or_env

DEFAULT_REPO_ID = "gpt2"
VALID_TASKS = ("text2text-generation", "text-generation", "summarization")


class HuggingFaceHub(LLM):
    """HuggingFaceHub  models.

    To use, you should have the ``huggingface_hub`` python package installed, and the
    environment variable ``HUGGINGFACEHUB_API_TOKEN`` set with your API token, or pass
    it as a named parameter to the constructor.

    Only supports `text-generation`, `text2text-generation` and `summarization` for now.

    Example:
        .. code-block:: python

            from langchain.llms import HuggingFaceHub
            hf = HuggingFaceHub(repo_id="gpt2", huggingfacehub_api_token="my-api-key")
    """

    client: Any = None  #: :meta private:
    repo_id: str = DEFAULT_REPO_ID
    """Model name to use."""
    task: Optional[str] = None
    """Task to call the model with.
    Should be a task that returns `generated_text` or `summary_text`."""
    model_kwargs: Optional[dict] = None
    """Key word arguments to pass to the model."""

    huggingfacehub_api_token: Optional[str] = None
    model_config = ConfigDict(extra="forbid")

    @model_validator()
    @classmethod
    def validate_environment(cls, values: Dict) -> Dict:
        """Validate that api key and python package exists in environment."""
        huggingfacehub_api_token = get_from_dict_or_env(
            values, "huggingfacehub_api_token", "HUGGINGFACEHUB_API_TOKEN"
        )
        try:
            from huggingface_hub.inference_api import InferenceApi

            repo_id = values["repo_id"]
            client = InferenceApi(
                repo_id=repo_id,
                token=huggingfacehub_api_token,
                task=values.get("task"),
            )
            if client.task not in VALID_TASKS:
                raise ValueError(
                    f"Got invalid task {client.task}, "
                    f"currently only {VALID_TASKS} are supported"
                )
            values["client"] = client
        except ImportError:
            raise ValueError(
                "Could not import huggingface_hub python package. "
                "Please install it with `pip install huggingface_hub`."
            )
        return values

    @property
    def _identifying_params(self) -> Mapping[str, Any]:
        """Get the identifying parameters."""
        _model_kwargs = self.model_kwargs or {}
        return {
            **{"repo_id": self.repo_id, "task": self.task},
            **{"model_kwargs": _model_kwargs},
        }

    @property
    def _llm_type(self) -> str:
        """Return type of llm."""
        return "huggingface_hub"

    def _call(
        self,
        prompt: str,
        stop: Optional[List[str]] = None,
        run_manager: Optional[CallbackManagerForLLMRun] = None,
        **kwargs: Any,
    ) -> str:
        """Call out to HuggingFace Hub's inference endpoint.

        Args:
            prompt: The prompt to pass into the model.
            stop: Optional list of stop words to use when generating.

        Returns:
            The string generated by the model.

        Example:
            .. code-block:: python

                response = hf("Tell me a joke.")
        """
        _model_kwargs = self.model_kwargs or {}
        params = {**_model_kwargs, **kwargs}
        response = self.client(inputs=prompt, params=params)
        if "error" in response:
            raise ValueError(f"Error raised by inference API: {response['error']}")
        if self.client.task == "text-generation":
            # Text generation return includes the starter text.
            text = response[0]["generated_text"][len(prompt) :]
        elif self.client.task == "text2text-generation":
            text = response[0]["generated_text"]
        elif self.client.task == "summarization":
            text = response[0]["summary_text"]
        else:
            raise ValueError(
                f"Got invalid task {self.client.task}, "
                f"currently only {VALID_TASKS} are supported"
            )
        if stop is not None:
            # This is a bit hacky, but I can't figure out a better way to enforce
            # stop tokens when making calls to huggingface_hub.
            text = enforce_stop_tokens(text, stop)
        return text
