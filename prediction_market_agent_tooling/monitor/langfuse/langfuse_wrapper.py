from functools import cached_property

from langfuse.callback import CallbackHandler
from pydantic import BaseModel, computed_field

from prediction_market_agent_tooling.config import APIKeys
from prediction_market_agent_tooling.tools.utils import utcnow


class LangfuseWrapper(BaseModel):
    agent_name: str

    @computed_field  # type: ignore[misc] # Mypy issue: https://github.com/python/mypy/issues/14461
    @cached_property
    def session_id(self) -> str:
        return f"{self.agent_name} - {utcnow()}"

    def get_langfuse_handler(self) -> CallbackHandler:
        keys = APIKeys()
        langfuse_handler = CallbackHandler(
            secret_key=keys.langfuse_secret_key.get_secret_value(),
            public_key=keys.langfuse_public_key.get_secret_value(),
            host=keys.langfuse_host,
            session_id=self.session_id,
        )
        return langfuse_handler
