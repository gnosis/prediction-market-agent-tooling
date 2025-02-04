import typing as t

from eth_typing import HexAddress
from pydantic import BaseModel, ConfigDict, Field
from web3.constants import ADDRESS_ZERO

from prediction_market_agent_tooling.gtypes import HexBytes


class CreateCategoricalMarketsParams(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    market_name: str = Field(..., alias="marketName")
    outcomes: list[str]
    # Only relevant for scalar markets
    question_start: t.Optional[str] = Field(alias="questionStart", default="")
    question_end: t.Optional[str] = Field(alias="questionEnd", default="")
    outcome_type: t.Optional[str] = Field(alias="outcomeType", default="")

    parent_outcome: t.Optional[int] = Field(alias="parentOutcome", default=0)
    parent_market: t.Optional[HexAddress] = Field(
        alias="parentMarket", default=ADDRESS_ZERO
    )

    category: t.Optional[str] = Field(default="misc")
    lang: t.Optional[str] = Field(default="en_US")

    lower_bound: t.Optional[int] = Field(alias="lowerBound", default=0)
    upper_bound: t.Optional[int] = Field(alias="upperBound", default=0)
    min_bond: int = Field(..., alias="minBond")
    opening_time: int = Field(..., alias="openingTime")
    token_names: list[str] = Field(..., alias="tokenNames")


class SeerParentMarket(BaseModel):
    id: HexBytes


class SeerMarket(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    publisher: str = Field(..., alias="publisherAddress")

    id: HexBytes
    title: str = Field(alias="marketName")
    outcomes: list[str]
    parent_market: SeerParentMarket | None = Field(alias="parentMarket")
    wrapped_tokens: list[HexBytes] = Field(alias="wrappedTokens")

    parent_outcome: t.Optional[str] = Field(..., alias="parentOutcome")
    parent_market: t.Optional[HexBytes] = Field(..., alias="parentMarket")


class SeerToken(BaseModel):
    id: HexBytes
    name: str
    symbol: str

    lower_bound: t.Optional[int] = Field(..., alias="lowerBound")
    upper_bound: t.Optional[int] = Field(..., alias="upperBound")
    min_bond: int = Field(..., alias="minBond")
    opening_time: int = Field(..., alias="openingTime")
    token_names: list[str] = Field(..., alias="tokenNames")


class SeerPool(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    id: HexBytes
    liquidity: int
    token0: SeerToken
    token1: SeerToken
