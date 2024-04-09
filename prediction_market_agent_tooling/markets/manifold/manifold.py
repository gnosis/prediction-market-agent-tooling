import typing as t
from datetime import datetime
from decimal import Decimal
from math import ceil

from prediction_market_agent_tooling.gtypes import Mana, Probability, mana_type
from prediction_market_agent_tooling.markets.agent_market import (
    AgentMarket,
    FilterBy,
    SortBy,
)
from prediction_market_agent_tooling.markets.data_models import BetAmount, Currency
from prediction_market_agent_tooling.markets.manifold.api import (
    get_manifold_binary_markets,
    place_bet,
)
from prediction_market_agent_tooling.markets.manifold.data_models import (
    MANIFOLD_BASE_URL,
    ManifoldMarket,
)
from prediction_market_agent_tooling.tools.betting_strategies.minimum_bet_to_win import (
    minimum_bet_to_win,
)


class ManifoldAgentMarket(AgentMarket):
    """
    Manifold's market class that can be used by agents to make predictions.
    """

    currency: t.ClassVar[Currency] = Currency.Mana
    base_url: t.ClassVar[str] = MANIFOLD_BASE_URL

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
            resolution=model.resolution,
            created_time=model.createdTime,
            close_time=model.closeTime,
            p_yes=Probability(model.probability),
            url=model.url,
            volume=model.volume,
        )

    @staticmethod
    def get_binary_markets(
        limit: int,
        sort_by: SortBy,
        filter_by: FilterBy = FilterBy.OPEN,
        created_after: t.Optional[datetime] = None,
        excluded_questions: set[str] | None = None,
    ) -> list["ManifoldAgentMarket"]:
        sort: t.Literal["newest", "close-date"] | None
        if sort_by == SortBy.CLOSING_SOONEST:
            sort = "close-date"
        elif sort_by == SortBy.NEWEST:
            sort = "newest"
        elif sort_by == SortBy.NONE:
            sort = None
        else:
            raise ValueError(f"Unknown sort_by: {sort_by}")

        filter_: t.Literal["open", "resolved"] | None
        if filter_by == FilterBy.OPEN:
            filter_ = "open"
        elif filter_by == FilterBy.RESOLVED:
            filter_ = "resolved"
        elif filter_by == FilterBy.NONE:
            filter_ = None
        else:
            raise ValueError(f"Unknown filter_by: {filter_by}")

        return [
            ManifoldAgentMarket.from_data_model(m)
            for m in get_manifold_binary_markets(
                limit=limit,
                sort=sort,
                created_after=created_after,
                filter_=filter_,
                excluded_questions=excluded_questions,
            )
        ]
