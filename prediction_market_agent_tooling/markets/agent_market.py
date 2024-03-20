import typing as t
from datetime import datetime
from decimal import Decimal
from enum import Enum

from pydantic import BaseModel

from prediction_market_agent_tooling.gtypes import Probability
from prediction_market_agent_tooling.markets.data_models import (
    BetAmount,
    Currency,
    Resolution,
)
from prediction_market_agent_tooling.tools.utils import should_not_happen


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

    id: str
    question: str
    outcomes: list[str]
    resolution: Resolution | None
    created_time: datetime | None
    p_yes: Probability

    @property
    def p_no(self) -> float:
        return 1 - self.p_yes

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

    def redeem_positions(self) -> None:
        print(
            "This should be implemented on each subclass. No positions are redeemed in this method."
        )
        return

    def before_process_bets(self) -> None:
        print(
            "This should be implemented on each subclass. No positions are redeemed in this method."
        )
        return

    def after_process_bets(self) -> None:
        print(
            "This should be implemented on each subclass. No positions are redeemed in this method."
        )
        return

    @staticmethod
    def get_binary_markets(
        limit: int,
        sort_by: SortBy,
        filter_by: FilterBy = FilterBy.OPEN,
        created_after: t.Optional[datetime] = None,
    ) -> list["AgentMarket"]:
        raise NotImplementedError("Subclasses must implement this method")

    def is_resolved(self) -> bool:
        return self.resolution is not None

    def has_successful_resolution(self) -> bool:
        return self.resolution in [Resolution.YES, Resolution.NO]

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
