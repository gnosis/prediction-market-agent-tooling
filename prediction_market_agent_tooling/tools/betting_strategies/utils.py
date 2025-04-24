from pydantic import BaseModel

from prediction_market_agent_tooling.gtypes import CollateralToken, OutcomeStr


class SimpleBet(BaseModel):
    direction: OutcomeStr
    size: CollateralToken
