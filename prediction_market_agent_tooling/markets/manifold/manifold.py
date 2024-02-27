import typing as t
from datetime import datetime
from decimal import Decimal
from math import ceil

from prediction_market_agent_tooling.gtypes import Mana, mana_type
from prediction_market_agent_tooling.markets.agent_market import (
    AgentMarket,
    FilterBy,
    SortBy,
)
from prediction_market_agent_tooling.markets.betting_strategies import (
    minimum_bet_to_win,
)
from prediction_market_agent_tooling.markets.data_models import BetAmount, Currency
from prediction_market_agent_tooling.markets.manifold.api import (
    get_manifold_binary_markets,
    place_bet,
)
from prediction_market_agent_tooling.markets.manifold.data_models import ManifoldMarket


class ManifoldAgentMarket(AgentMarket):
    """
    Manifold's market class that can be used by agents to make predictions.
    """

    currency: t.ClassVar[Currency] = Currency.Mana

    def get_tiny_bet_amount(self) -> BetAmount:
        return BetAmount(amount=Decimal(1), currency=self.currency)

    def get_minimum_bet_to_win(self, answer: bool, amount_to_win: float) -> Mana:
        # Manifold lowest bet is 1 Mana, so we need to ceil the result.
        return mana_type(ceil(minimum_bet_to_win(answer, amount_to_win, self)))

    def place_bet(self, outcome: bool, amount: BetAmount) -> None:
        if amount.currency != self.currency:
            raise ValueError(f"Manifold bets are made in Mana. Got {amount.currency}.")
        place_bet(
            amount=Mana(amount.amount),
            market_id=self.id,
            outcome=outcome,
        )

    @staticmethod
    def from_data_model(model: ManifoldMarket) -> "ManifoldAgentMarket":
        return ManifoldAgentMarket(
            id=model.id,
            question=model.question,
            outcomes=model.outcomes,
            resolution=model.get_resolution_enum() if model.isResolved else None,
            created_time=model.createdTime,
            p_yes=model.probability,
        )

    @staticmethod
    def get_binary_markets(
        limit: int,
        sort_by: SortBy,
        filter_by: FilterBy = FilterBy.OPEN,
        created_after: t.Optional[datetime] = None,
    ) -> list[AgentMarket]:
        sort: t.Literal[ "newest", "close-date"]
        if sort_by == SortBy.CLOSING_SOONEST:
            sort = "close-date"
        elif sort_by == SortBy.NEWEST:
            sort = "newest"
        else:
            raise ValueError(f"Unknown sort_by: {sort_by}")

        filter_: t.Literal["open", "resolved"]
        if filter_by == FilterBy.OPEN:
            filter_ = "open"
        elif filter_by == FilterBy.RESOLVED:
            filter_ = "resolved"
        else:
            raise ValueError(f"Unknown filter_by: {filter_by}")

        return [
            ManifoldAgentMarket.from_data_model(m)
            for m in get_manifold_binary_markets(
                limit=limit,
                sort=sort,
                created_after=created_after,
                filter_=filter_,
            )
        ]
