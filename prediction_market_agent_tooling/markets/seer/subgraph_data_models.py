from pydantic import BaseModel, ConfigDict, Field
from web3 import Web3
from web3.constants import ADDRESS_ZERO

from prediction_market_agent_tooling.gtypes import (
    ChecksumAddress,
    CollateralToken,
    HexAddress,
    HexBytes,
    OutcomeStr,
    OutcomeToken,
    Wei,
)
from prediction_market_agent_tooling.tools.datetime_utc import DatetimeUTC


class SwaprToken(BaseModel):
    id: HexBytes
    name: str
    symbol: str

    @property
    def address(self) -> ChecksumAddress:
        return Web3.to_checksum_address(self.id.hex())


class SwaprPool(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    id: HexBytes
    liquidity: int
    token0: SwaprToken
    token1: SwaprToken
    token0Price: CollateralToken
    token1Price: CollateralToken
    sqrtPrice: int
    totalValueLockedToken0: float
    totalValueLockedToken1: float


class SwaprSwap(BaseModel):
    id: str  # It's like "0x73afd8f096096552d72a0b40ea66d2076be136c6a531e2f6b190d151a750271e#32" (note the #32) # web3-private-key-ok
    recipient: HexAddress
    sender: HexAddress
    price: Wei
    amount0: CollateralToken
    amount1: CollateralToken
    token0: SwaprToken
    token1: SwaprToken
    timestamp: int

    @property
    def timestamp_utc(self) -> DatetimeUTC:
        return DatetimeUTC.to_datetime_utc(self.timestamp)

    @property
    def added_to_pool(self) -> CollateralToken:
        return self.amount0 if self.amount0 > 0 else self.amount1

    @property
    def withdrawn_from_pool(self) -> OutcomeToken:
        return (
            OutcomeToken(abs(self.amount0).value)
            if self.amount0 < 0
            else OutcomeToken(abs(self.amount1).value)
        )


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
    min_bond: int = Field(
        ..., alias="minBond"
    )  # typed as int for later .model_dump() usage (if using Wei, other keys also exported)
    opening_time: int = Field(..., alias="openingTime")
    token_names: list[str] = Field(..., alias="tokenNames")
