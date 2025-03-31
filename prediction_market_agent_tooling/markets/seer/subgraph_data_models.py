from pydantic import BaseModel, ConfigDict, Field
from web3.constants import ADDRESS_ZERO

from prediction_market_agent_tooling.gtypes import (
    CollateralToken,
    HexAddress,
    HexBytes,
    OutcomeStr,
    Wei,
)


class SeerToken(BaseModel):
    id: HexBytes
    name: str
    symbol: str


class SeerPool(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    id: HexBytes
    liquidity: int
    token0: SeerToken
    token1: SeerToken
    token0Price: CollateralToken
    token1Price: CollateralToken
    sqrtPrice: int


class NewMarketEvent(BaseModel):
    market: HexAddress
    marketName: str
    parentMarket: HexAddress
    conditionId: HexBytes
    questionId: HexBytes
    questionsIds: list[HexBytes]


class CreateCategoricalMarketsParams(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    market_name: str = Field(..., alias="marketName")
    outcomes: list[OutcomeStr]
    # Only relevant for scalar markets
    question_start: str = Field(alias="questionStart", default="")
    question_end: str = Field(alias="questionEnd", default="")
    outcome_type: str = Field(alias="outcomeType", default="")

    # Not needed for non-conditional markets.
    parent_outcome: int = Field(alias="parentOutcome", default=0)
    parent_market: HexAddress = Field(alias="parentMarket", default=ADDRESS_ZERO)

    category: str
    lang: str
    lower_bound: int = Field(alias="lowerBound", default=0)
    upper_bound: int = Field(alias="upperBound", default=0)
    min_bond: Wei = Field(..., alias="minBond")
    opening_time: int = Field(..., alias="openingTime")
    token_names: list[str] = Field(..., alias="tokenNames")


class SeerParentMarket(BaseModel):
    id: HexBytes
