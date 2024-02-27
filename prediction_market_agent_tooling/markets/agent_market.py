import typing as t
from datetime import datetime
from decimal import Decimal
from enum import Enum

from pydantic import BaseModel

from prediction_market_agent_tooling.markets.data_models import (
    BetAmount,
    Currency,
    Resolution,
)


class SortBy(str, Enum):
    CLOSING_SOONEST = "closing-soonest"
    NEWEST = "newest"


class FilterBy(str, Enum):
    OPEN = "open"
    CLOSED = "closed"


class AgentMarket(BaseModel):
    """
    Common market class that can be created from vendor specific markets.
    Contains everything that is needed for an agent to make a prediction.
    """

    id: str
    question: str
    outcomes: list[str]
    currency: t.ClassVar[Currency]
    resolution: t.Optional[Resolution] = None
    created_time: datetime
    p_yes: float

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
    ) -> list["AgentMarket"]:
        raise NotImplementedError("Subclasses must implement this method")

    def is_resolved(self) -> bool:
        return self.resolution is not None

    def has_successful_resolution(self) -> bool:
        return self.resolution in [Resolution.YES, Resolution.NO]

    def get_outcome_index(self, outcome: str) -> int:
        try:
            return self.outcomes.index(outcome)
        except ValueError:
            raise ValueError(f"Outcome `{outcome}` not found in `{self.outcomes}`.")
