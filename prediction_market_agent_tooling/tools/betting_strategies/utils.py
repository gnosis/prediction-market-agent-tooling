from pydantic import BaseModel

from prediction_market_agent_tooling.gtypes import Token


class SimpleBet(BaseModel):
    direction: bool
    size: Token
