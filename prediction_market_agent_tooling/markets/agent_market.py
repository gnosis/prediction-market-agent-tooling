import typing as t
from datetime import datetime
from decimal import Decimal
from enum import Enum

from pydantic import BaseModel, field_validator

from prediction_market_agent_tooling.gtypes import Probability
from prediction_market_agent_tooling.markets.data_models import (
    BetAmount,
    Currency,
    Resolution,
    TokenAmount,
)
from prediction_market_agent_tooling.tools.utils import (
    add_utc_timezone_validator,
    check_not_none,
    should_not_happen,
)


class SortBy(str, Enum):
    CLOSING_SOONEST = "closing-soonest"
    NEWEST = "newest"
    NONE = "none"


class FilterBy(str, Enum):
    OPEN = "open"
    RESOLVED = "resolved"
    NONE = "none"


class AgentMarket(BaseModel):
    """
    Common market class that can be created from vendor specific markets.
    Contains everything that is needed for an agent to make a prediction.
    """

    currency: t.ClassVar[Currency]
    base_url: t.ClassVar[str]

    id: str
    question: str
    outcomes: list[str]
    resolution: Resolution | None
    created_time: datetime | None
    close_time: datetime
    p_yes: Probability
    url: str
    volume: Decimal | None  # Should be in currency of `currency` above.

    _add_timezone_validator_created_time = field_validator("created_time")(
        add_utc_timezone_validator
    )
    _add_timezone_validator_close_time = field_validator("close_time")(
        add_utc_timezone_validator
    )

    @property
    def p_no(self) -> Probability:
        return Probability(1 - self.p_yes)

    @property
    def yes_outcome_price(self) -> Decimal:
        """
        Price at prediction market is equal to the probability of given outcome.
        Keep as an extra property, in case it wouldn't be true for some prediction market platform.
        """
        return Decimal(self.p_yes)

    @property
    def no_outcome_price(self) -> Decimal:
        """
        Price at prediction market is equal to the probability of given outcome.
        Keep as an extra property, in case it wouldn't be true for some prediction market platform.
        """
        return Decimal(self.p_no)

    @property
    def probable_resolution(self) -> Resolution:
        if self.is_resolved():
            if self.has_successful_resolution():
                return check_not_none(self.resolution)
            else:
                raise ValueError(f"Unknown resolution: {self.resolution}")
        else:
            return Resolution.YES if self.p_yes > 0.5 else Resolution.NO

    @property
    def boolean_outcome(self) -> bool:
        if self.resolution:
            if self.resolution == Resolution.YES:
                return True
            elif self.resolution == Resolution.NO:
                return False
        should_not_happen(f"Market {self.id} does not have a successful resolution.")

    def get_bet_amount(self, amount: Decimal) -> BetAmount:
        return BetAmount(amount=amount, currency=self.currency)

    def get_tiny_bet_amount(self) -> BetAmount:
        raise NotImplementedError("Subclasses must implement this method")

    def place_bet(self, outcome: bool, amount: BetAmount) -> None:
        raise NotImplementedError("Subclasses must implement this method")

    @staticmethod
    def get_binary_markets(
        limit: int,
        sort_by: SortBy,
        filter_by: FilterBy = FilterBy.OPEN,
        created_after: t.Optional[datetime] = None,
        excluded_questions: set[str] | None = None,
    ) -> t.Sequence["AgentMarket"]:
        raise NotImplementedError("Subclasses must implement this method")

    @staticmethod
    def get_binary_market(id: str) -> "AgentMarket":
        raise NotImplementedError("Subclasses must implement this method")

    def is_resolved(self) -> bool:
        return self.resolution is not None

    def has_successful_resolution(self) -> bool:
        return self.resolution in [Resolution.YES, Resolution.NO]

    def has_unsuccessful_resolution(self) -> bool:
        return self.resolution in [Resolution.CANCEL, Resolution.MKT]

    def get_outcome_str(self, outcome_index: int) -> str:
        try:
            return self.outcomes[outcome_index]
        except IndexError:
            raise IndexError(
                f"Outcome index `{outcome_index}` out of range for `{self.outcomes}`: `{self.outcomes}`."
            )

    def get_outcome_index(self, outcome: str) -> int:
        try:
            return self.outcomes.index(outcome)
        except ValueError:
            raise ValueError(f"Outcome `{outcome}` not found in `{self.outcomes}`.")

    def get_squared_error(self) -> float:
        return (self.p_yes - self.boolean_outcome) ** 2

    def get_token_balance(self, user_id: str, outcome: str) -> TokenAmount:
        raise NotImplementedError("Subclasses must implement this method")
