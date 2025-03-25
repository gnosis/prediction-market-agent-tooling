import re
import typing as t
from enum import Enum
from urllib.parse import urljoin

from pydantic import BaseModel, ConfigDict, Field
from web3 import Web3

from prediction_market_agent_tooling.config import RPCConfig
from prediction_market_agent_tooling.gtypes import (
    ChecksumAddress,
    HexAddress,
    HexBytes,
    Probability,
)
from prediction_market_agent_tooling.markets.data_models import Resolution
from prediction_market_agent_tooling.markets.seer.price_manager import PriceManager
from prediction_market_agent_tooling.markets.seer.subgraph_data_models import (
    SeerParentMarket,
)
from prediction_market_agent_tooling.tools.datetime_utc import DatetimeUTC


class SeerOutcomeEnum(str, Enum):
    YES = "yes"
    NO = "no"
    INVALID = "invalid"

    @classmethod
    def from_bool(cls, value: bool) -> "SeerOutcomeEnum":
        return cls.YES if value else cls.NO

    @classmethod
    def from_string(cls, value: str) -> "SeerOutcomeEnum":
        """Convert a string (case-insensitive) to an Outcome enum."""
        normalized = value.strip().lower()
        patterns = {
            r"^yes$": cls.YES,
            r"^no$": cls.NO,
            r"^(invalid|invalid result)$": cls.INVALID,
        }

        # Search through patterns and return the first match
        for pattern, outcome in patterns.items():
            if re.search(pattern, normalized):
                return outcome

        raise ValueError(f"Could not map {value=} to an outcome.")

    def to_bool(self) -> bool:
        """Convert a SeerOutcomeEnum to a boolean value."""
        if self == self.YES:
            return True
        elif self == self.NO:
            return False
        elif self == self.INVALID:
            raise ValueError("Cannot convert INVALID outcome to boolean.")
        else:
            raise ValueError(f"Unknown outcome: {self}")


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
    collateral_token: HexAddress = Field(alias="collateralToken")
    condition_id: HexBytes = Field(alias="conditionId")
    opening_ts: int = Field(alias="openingTs")
    block_timestamp: int = Field(alias="blockTimestamp")
    has_answers: bool | None = Field(alias="hasAnswers")
    payout_reported: bool = Field(alias="payoutReported")
    payout_numerators: list[int] = Field(alias="payoutNumerators")
    outcomes_supply: int = Field(alias="outcomesSupply")

    @property
    def has_valid_answer(self) -> bool:
        # We assume that, for the market to be resolved as invalid, it must have both:
        # 1. An invalid outcome AND
        # 2. Invalid payoutNumerator is 1.

        try:
            self.outcome_as_enums[SeerOutcomeEnum.INVALID]
        except KeyError:
            raise ValueError(
                f"Market {self.id.hex()} has no invalid outcome. {self.outcomes}"
            )

        return self.payout_reported and self.payout_numerators[-1] != 1

    @property
    def outcome_as_enums(self) -> dict[SeerOutcomeEnum, int]:
        return {
            SeerOutcomeEnum.from_string(outcome): idx
            for idx, outcome in enumerate(self.outcomes)
        }

    @property
    def is_resolved(self) -> bool:
        return self.payout_reported

    @property
    def is_resolved_with_valid_answer(self) -> bool:
        return self.is_resolved and self.has_valid_answer

    def get_resolution_enum(self) -> t.Optional[Resolution]:
        if not self.is_resolved_with_valid_answer:
            return None

        max_idx = self.payout_numerators.index(1)

        outcome: str = self.outcomes[max_idx]
        outcome_enum = SeerOutcomeEnum.from_string(outcome)
        if outcome_enum.to_bool():
            return Resolution.YES
        return Resolution.NO

    @property
    def is_binary(self) -> bool:
        # 3 because Seer has also third, `Invalid` outcome.
        return len(self.outcomes) == 3

    def boolean_outcome_from_answer(self, answer: HexBytes) -> bool:
        if not self.is_binary:
            raise ValueError(
                f"Market with title {self.title} is not binary, it has {len(self.outcomes)} outcomes."
            )

        outcome: str = self.outcomes[answer.as_int()]
        outcome_enum = SeerOutcomeEnum.from_string(outcome)
        return outcome_enum.to_bool()

    def get_resolution_enum_from_answer(self, answer: HexBytes) -> Resolution:
        if self.boolean_outcome_from_answer(answer):
            return Resolution.YES
        else:
            return Resolution.NO

    @property
    def collateral_token_contract_address_checksummed(self) -> ChecksumAddress:
        return Web3.to_checksum_address(self.collateral_token)

    @property
    def close_time(self) -> DatetimeUTC:
        return DatetimeUTC.to_datetime_utc(self.opening_ts)

    @property
    def created_time(self) -> DatetimeUTC:
        return DatetimeUTC.to_datetime_utc(self.block_timestamp)

    @property
    def current_p_yes(self) -> Probability:
        p = PriceManager(self)
        return p.current_market_p_yes

    @property
    def url(self) -> str:
        chain_id = RPCConfig().chain_id
        return urljoin(SEER_BASE_URL, f"markets/{chain_id}/{self.id.hex()}")
