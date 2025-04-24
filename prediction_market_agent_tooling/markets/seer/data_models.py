import re
import typing as t
from enum import Enum
from urllib.parse import urljoin

from pydantic import BaseModel, ConfigDict, Field
from web3 import Web3
from web3.constants import ADDRESS_ZERO

from prediction_market_agent_tooling.config import RPCConfig
from prediction_market_agent_tooling.gtypes import (
    ChecksumAddress,
    HexAddress,
    HexBytes,
    OutcomeStr,
    OutcomeWei,
    Web3Wei,
)
from prediction_market_agent_tooling.markets.data_models import Resolution
from prediction_market_agent_tooling.markets.seer.subgraph_data_models import (
    SeerParentMarket,
)
from prediction_market_agent_tooling.tools.contract import ContractERC20OnGnosisChain
from prediction_market_agent_tooling.tools.datetime_utc import DatetimeUTC


class CreateCategoricalMarketsParams(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    market_name: str = Field(..., alias="marketName")
    outcomes: t.Sequence[OutcomeStr]
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
    min_bond: Web3Wei = Field(..., alias="minBond")
    opening_time: int = Field(..., alias="openingTime")
    token_names: list[str] = Field(..., alias="tokenNames")


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
    outcomes: t.Sequence[OutcomeStr]
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

    def is_redeemable(self, owner: ChecksumAddress, web3: Web3 | None = None) -> bool:
        token_balances = self.get_outcome_token_balances(owner, web3)
        if not self.payout_reported:
            return False
        return any(
            payout and balance > 0
            for payout, balance in zip(self.payout_numerators, token_balances)
        )

    def get_outcome_token_balances(
        self, owner: ChecksumAddress, web3: Web3 | None = None
    ) -> list[OutcomeWei]:
        return [
            OutcomeWei.from_wei(
                ContractERC20OnGnosisChain(
                    address=Web3.to_checksum_address(token)
                ).balanceOf(owner, web3=web3)
            )
            for token in self.wrapped_tokens
        ]

    @property
    def is_binary(self) -> bool:
        # 3 because Seer has also third, `Invalid` outcome.
        return len(self.outcomes) == 3 and {"yes", "no"}.issubset(
            {o.lower() for o in self.outcomes}
        )

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
    def url(self) -> str:
        chain_id = RPCConfig().chain_id
        return urljoin(SEER_BASE_URL, f"markets/{chain_id}/{self.id.hex()}")


class RedeemParams(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    market: ChecksumAddress
    outcome_indices: list[int] = Field(alias="outcomeIndexes")
    amounts: list[OutcomeWei]
