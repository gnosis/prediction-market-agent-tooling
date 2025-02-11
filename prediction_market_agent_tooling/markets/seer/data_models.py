import typing as t

from pydantic import BaseModel, ConfigDict, Field
from web3 import Web3
from web3.constants import ADDRESS_ZERO

from prediction_market_agent_tooling.config import RPCConfig
from prediction_market_agent_tooling.gtypes import (
    HexBytes,
    Wei,
    Probability,
    HexAddress,
    ChecksumAddress,
)
from prediction_market_agent_tooling.markets.data_models import Resolution
from prediction_market_agent_tooling.tools.datetime_utc import DatetimeUTC
from prediction_market_agent_tooling.tools.utils import check_not_none


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


SEER_BASE_URL = "https://presagio.pages.dev"


class SeerMarket(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    id: HexBytes
    creator: HexAddress
    title: str = Field(alias="marketName")
    outcomes: list[str]
    wrapped_tokens: list[HexAddress] = Field(alias="wrappedTokens")
    parent_outcome: int = Field(alias="parentOutcome")
    parent_market: t.Optional[SeerParentMarket] = Field(
        alias="parentMarket", default=None
    )
    collateralToken: HexAddress
    conditionId: HexBytes
    openingTs: int
    blockTimestamp: int
    hasAnswers: bool | None
    payoutReported: bool
    payoutNumerators: list[int]

    @property
    def has_valid_answer(self) -> bool:
        # We assume that, for the market to be resolved as invalid, it must have
        # 1. 3 outcomes (Yes, No, Invalid), 2. Invalid is the last one and 3. Invalid numerator is 1.
        if len(self.outcomes) != 3:
            raise ValueError(
                f"Market {self.id} must have 3 outcomes. Actual outcomes - {self.outcomes}"
            )
        return self.payoutReported and self.payoutNumerators[-1] != 1

    @property
    def is_resolved(self) -> bool:
        return self.payoutReported

    @property
    def is_resolved_with_valid_answer(self) -> bool:
        return self.is_resolved and self.has_valid_answer

    def get_resolution_enum(self) -> t.Optional[Resolution]:
        if not self.is_resolved_with_valid_answer:
            return None
        return self.get_resolution_enum_from_answer(
            check_not_none(
                self.currentAnswer, "Can not be None if `is_resolved_with_valid_answer`"
            )
        )

    @property
    def collateral_token_contract_address_checksummed(self) -> ChecksumAddress:
        return Web3.to_checksum_address(self.collateralToken)

    @property
    def close_time(self) -> DatetimeUTC:
        return DatetimeUTC.to_datetime_utc(self.openingTs)

    @property
    def created_time(self) -> DatetimeUTC:
        return DatetimeUTC.to_datetime_utc(self.blockTimestamp)

    @property
    def current_p_yes(self) -> Probability:
        # ToDo - Fetch from pools (see useMarketOdds.ts from seer-demo)
        return Probability(0.123)

    @property
    def url(self) -> str:
        chain_id = RPCConfig().chain_id
        return f"{SEER_BASE_URL}/markets/{chain_id}/{self.id.hex()}"


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
