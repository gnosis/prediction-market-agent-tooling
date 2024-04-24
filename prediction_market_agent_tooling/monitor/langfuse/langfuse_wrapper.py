from pydantic import BaseModel
from langfuse.callback import CallbackHandler
from prediction_market_agent_tooling.tools.utils import utcnow


class LangfuseWrapper(BaseModel):
    agent_name: str

    @property
    def session_id(self) -> str | None:
        return f"{self.agent_name} - {utcnow()}"

    def get_langfuse_handler(self):
        langfuse_handler = CallbackHandler(
            secret_key=self.keys.langfuse_secret_key.get_secret_value(),
            public_key=self.keys.langfuse_public_key.get_secret_value(),
            host=self.keys.langfuse_host,
            session_id=self.session_id,
        )
        return langfuse_handler
