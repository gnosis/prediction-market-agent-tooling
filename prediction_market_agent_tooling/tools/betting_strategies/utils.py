from pydantic import BaseModel

from prediction_market_agent_tooling.gtypes import CollateralToken


class BinaryKellyBet(BaseModel):
    direction: bool
    size: CollateralToken


class CategoricalKellyBet(BaseModel):
    index: int
    size: CollateralToken
