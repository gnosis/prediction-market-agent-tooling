import re
import typing as t
from enum import Enum
from urllib.parse import urljoin

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
    xdai_type,
)
from prediction_market_agent_tooling.loggers import logger
from prediction_market_agent_tooling.markets.data_models import Resolution
from prediction_market_agent_tooling.markets.omen.data_models import get_boolean_outcome
from prediction_market_agent_tooling.tools.cow.cow_manager import CowManager
from prediction_market_agent_tooling.tools.datetime_utc import DatetimeUTC
from prediction_market_agent_tooling.tools.web3_utils import xdai_to_wei


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


class SeerOutcomeEnum(str, Enum):
    POSITIVE = "positive"
    NEGATIVE = "negative"
    NEUTRAL = "neutral"

    @classmethod
    def from_bool(cls, value: bool) -> "SeerOutcomeEnum":
        return cls.POSITIVE if value else cls.NEGATIVE

    @classmethod
    def from_string(cls, value: str):
        """Convert a string (case-insensitive) to an Outcome enum."""
        normalized = value.strip().lower()
        # mapping = {
        #     "yes": cls.POSITIVE,
        #     "no": cls.NEGATIVE,
        #     "invalid": cls.NEUTRAL,
        # }
        # Define regex patterns for matching
        patterns = {
            r"^yes$": cls.POSITIVE,
            r"^no$": cls.NEGATIVE,
            r"^(invalid|invalid result)$": cls.NEUTRAL,
        }

        # Search through patterns and return the first match
        for pattern, outcome in patterns.items():
            if re.search(pattern, normalized):
                return outcome

        # Explicitly fail for non-binary markets by returning None if no match is found
        raise ValueError(f"Could not map {value=} to an outcome.")


class SeerParentMarket(BaseModel):
    id: HexBytes


SEER_BASE_URL = "https://app.seer.pm"


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
                f"Market {self.id.hex()} must have 3 outcomes. Actual outcomes - {self.outcomes}"
            )
        return self.payoutReported and self.payoutNumerators[-1] != 1

    @property
    def outcome_as_enums(self) -> dict[SeerOutcomeEnum, int]:
        return {
            SeerOutcomeEnum.from_string(outcome): idx
            for idx, outcome in enumerate(self.outcomes)
        }

    @property
    def is_resolved(self) -> bool:
        return self.payoutReported

    @property
    def is_resolved_with_valid_answer(self) -> bool:
        return self.is_resolved and self.has_valid_answer

    def get_resolution_enum(self) -> t.Optional[Resolution]:
        if not self.is_resolved_with_valid_answer:
            return None

        # ToDo - Test in a resolved market to see if calculation below is correct.
        max_idx = self.payoutNumerators.index(1)

        bool_outcome = get_boolean_outcome(self.outcomes[max_idx])
        if bool_outcome:
            return Resolution.YES
        return Resolution.NO

    @property
    def is_binary(self) -> bool:
        return len(self.outcomes) == 3

    def boolean_outcome_from_answer(self, answer: HexBytes) -> bool:
        if not self.is_binary:
            raise ValueError(
                f"Market with title {self.title} is not binary, it has {len(self.outcomes)} outcomes."
            )
        outcome: str = self.outcomes[answer.as_int()]
        return get_boolean_outcome(outcome)

    def get_resolution_enum_from_answer(self, answer: HexBytes) -> Resolution:
        if self.boolean_outcome_from_answer(answer):
            return Resolution.YES
        else:
            return Resolution.NO

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
        # ToDo - Write test
        # build a dict [OutcomeStr(), price]
        price_data = {}
        for idx in range(len(self.outcomes)):
            wrapped_token = self.wrapped_tokens[idx]
            price = self._get_price_for_token(
                token=Web3.to_checksum_address(wrapped_token)
            )
            price_data[idx] = price

        yes_idx = 0
        for idx, outcome in enumerate(self.outcomes):
            if outcome.lower() == "YES".lower():
                yes_idx = idx
                break

        price_yes = price_data[yes_idx] / sum(price_data.values())
        return Probability(price_yes)

    def _get_price_for_token(self, token: ChecksumAddress) -> float:
        collateral_exchange_amount = xdai_to_wei(xdai_type(1))
        try:
            quote = CowManager().get_quote(
                collateral_token=self.collateral_token_contract_address_checksummed,
                buy_token=token,
                sell_amount=collateral_exchange_amount,
            )
        except Exception as e:
            logger.warning(f"Could not get quote for {token=}, returning price 0. {e=}")
            return 0

        return collateral_exchange_amount / (float(quote.quote.buyAmount.root))

    @property
    def url(self) -> str:
        chain_id = RPCConfig().chain_id
        return urljoin(SEER_BASE_URL, f"markets/{chain_id}/{self.id.hex()}")


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
