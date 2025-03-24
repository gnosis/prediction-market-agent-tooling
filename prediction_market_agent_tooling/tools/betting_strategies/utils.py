from pydantic import BaseModel

from prediction_market_agent_tooling.gtypes import CollateralToken


class SimpleBet(BaseModel):
    direction: bool
    size: CollateralToken
