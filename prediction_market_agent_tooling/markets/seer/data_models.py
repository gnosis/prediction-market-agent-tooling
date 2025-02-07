import typing as t

from eth_typing import HexAddress
from pydantic import BaseModel, ConfigDict, Field
from web3.constants import ADDRESS_ZERO

from prediction_market_agent_tooling.gtypes import HexBytes, Wei

SEER_TRUE_OUTCOME = "Yes"
SEER_FALSE_OUTCOME = "No"


def get_bet_outcome(binary_outcome: bool) -> str:
    return SEER_TRUE_OUTCOME if binary_outcome else SEER_FALSE_OUTCOME


class CreateCategoricalMarketsParams(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    market_name: str = Field(..., alias="marketName")
    outcomes: list[str]
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


class SeerMarket(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    id: HexBytes
    title: str = Field(alias="marketName")
    outcomes: list[str]
    wrapped_tokens: list[HexBytes] = Field(alias="wrappedTokens")
    parent_outcome: int = Field(alias="parentOutcome")
    parent_market: t.Optional[SeerParentMarket] = Field(
        alias="parentMarket", default=None
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


class NewMarketEvent(BaseModel):
    market: HexAddress
    marketName: str
    parentMarket: HexAddress
    conditionId: HexBytes
    questionId: HexBytes
    questionsIds: list[HexBytes]
