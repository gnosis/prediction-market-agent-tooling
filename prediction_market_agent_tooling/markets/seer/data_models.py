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
    xdai_type,
)
from prediction_market_agent_tooling.loggers import logger
from prediction_market_agent_tooling.markets.data_models import Resolution
from prediction_market_agent_tooling.markets.seer.subgraph_data_models import (
    SeerParentMarket,
    SeerPool,
)
from prediction_market_agent_tooling.tools.caches.inmemory_cache import (
    persistent_inmemory_cache,
)
from prediction_market_agent_tooling.tools.cow.cow_manager import CowManager
from prediction_market_agent_tooling.tools.datetime_utc import DatetimeUTC
from prediction_market_agent_tooling.tools.web3_utils import xdai_to_wei


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

    @persistent_inmemory_cache
    def get_price_for_token(
        self,
        token: ChecksumAddress,
    ) -> float:
        collateral_exchange_amount = xdai_to_wei(xdai_type(1))
        try:
            quote = CowManager().get_quote(
                collateral_token=self.collateral_token_contract_address_checksummed,
                buy_token=token,
                sell_amount=collateral_exchange_amount,
            )
        except Exception as e:
            logger.warning(
                f"Could not get quote for {token=} from Cow, exception {e=}. Falling back to pools. "
            )
            price = self.get_token_price_from_pools(token=token)
            return price

        return collateral_exchange_amount / float(quote.quote.buyAmount.root)

    @staticmethod
    def _pool_token0_matches_token(token: ChecksumAddress, pool: SeerPool) -> bool:
        return pool.token0.id.hex().lower() == token.lower()

    def get_token_price_from_pools(
        self,
        token: ChecksumAddress,
        collateral_token_contract_address_checksummed: ChecksumAddress,
    ) -> float:
        pool = self.subgraph_handler.get_pool_by_token(token_address=token)

        if not pool:
            logger.warning(f"Could not find a pool for {token=}, returning 0.")
            return 0
        # Check if other token is market's collateral (sanity check).

        collateral_address = (
            pool.token0.id
            if self._pool_token0_matches_token(token=token, pool=pool)
            else pool.token1.id
        )
        if (
            collateral_address.hex().lower()
            != collateral_token_contract_address_checksummed.lower()
        ):
            logger.warning(
                f"Pool {pool.id.hex()} has collateral mismatch with market. Collateral from pool {collateral_address.hex()}, collateral from market {collateral_token_contract_address_checksummed}, returning 0."
            )
            return 0

        price_in_collateral_units = (
            pool.token0Price
            if self._pool_token0_matches_token(pool)
            else pool.token1Price
        )
        return price_in_collateral_units

    @property
    def current_p_yes(self) -> Probability:
        price_data = {}
        for idx, wrapped_token in enumerate(self.wrapped_tokens):
            price = self.get_price_for_token(
                token=Web3.to_checksum_address(wrapped_token),
            )

            price_data[idx] = price

        if sum(price_data.values()) == 0:
            logger.warning(
                f"Could not get p_yes for market {self.id.hex()}, all price quotes are 0."
            )
            return Probability(0)

        price_yes = price_data[self.outcome_as_enums[SeerOutcomeEnum.YES]]
        price_no = price_data[self.outcome_as_enums[SeerOutcomeEnum.NO]]
        if price_yes and not price_no:
            # We simply return p_yes since it's probably a bug that p_no wasn't found.
            return Probability(price_yes)
        elif price_no and not price_yes:
            # We return the complement of p_no (and ignore invalid).
            return Probability(1.0 - price_no)
        else:
            # If all prices are available, we normalize price_yes by the other prices for the final probability.
            price_yes = price_yes / sum(price_data.values())
            return Probability(price_yes)

    @property
    def url(self) -> str:
        chain_id = RPCConfig().chain_id
        return urljoin(SEER_BASE_URL, f"markets/{chain_id}/{self.id.hex()}")
