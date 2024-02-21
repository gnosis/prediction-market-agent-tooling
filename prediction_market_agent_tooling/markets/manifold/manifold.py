import typing as t
from decimal import Decimal

from prediction_market_agent_tooling.gtypes import Mana
from prediction_market_agent_tooling.markets.agent_market import AgentMarket
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
        )

    @staticmethod
    def get_binary_markets(limit: int) -> list[AgentMarket]:
        return [
            ManifoldAgentMarket.from_data_model(m)
            for m in get_manifold_binary_markets(limit=limit, sort="close-date")
        ]
