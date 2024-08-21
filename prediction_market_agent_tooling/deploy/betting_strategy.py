from abc import ABC, abstractmethod

from prediction_market_agent_tooling.markets.agent_market import AgentMarket
from prediction_market_agent_tooling.markets.data_models import (
    Answer,
    TokenAmountAndDirection,
)
from prediction_market_agent_tooling.tools.betting_strategies.kelly_criterion import (
    get_kelly_bet,
)


class BettingStrategy(ABC):
    @abstractmethod
    def calculate_bet_amount_and_direction(
        self, answer: Answer, market: AgentMarket
    ) -> TokenAmountAndDirection:
        pass


class FixedBetBettingStrategy(BettingStrategy):
    def calculate_bet_amount_and_direction(
        self, answer: Answer, market: AgentMarket
    ) -> TokenAmountAndDirection:
        bet_amount = market.get_tiny_bet_amount().amount
        return TokenAmountAndDirection(
            amount=bet_amount,
            currency=market.currency,
            direction=answer.decision,
        )


class KellyBettingStrategy(BettingStrategy):
    @staticmethod
    def get_max_bet_amount_for_market() -> float:
        # No difference between markets.
        return 10  # Mana or xDAI

    def calculate_bet_amount_and_direction(
        self, answer: Answer, market: AgentMarket
    ) -> TokenAmountAndDirection:
        max_bet_amount = self.get_max_bet_amount_for_market()
        kelly_bet = get_kelly_bet(
            max_bet_amount, market.current_p_yes, answer.p_yes, answer.confidence
        )
        return TokenAmountAndDirection(
            amount=kelly_bet.size,
            currency=market.currency,
            direction=kelly_bet.direction,
        )
