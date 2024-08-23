from abc import ABC, abstractmethod

from prediction_market_agent_tooling.markets.agent_market import AgentMarket
from prediction_market_agent_tooling.markets.data_models import (
    ProbabilisticAnswer,
    TokenAmountAndDirection,
)
from prediction_market_agent_tooling.tools.betting_strategies.kelly_criterion import (
    get_kelly_bet,
)


class BettingStrategy(ABC):
    def __init__(self, bet_amount: float | None = None):
        self.bet_amount = bet_amount

    @abstractmethod
    def calculate_bet_amount_and_direction(
        self, answer: ProbabilisticAnswer, market: AgentMarket
    ) -> TokenAmountAndDirection:
        pass


class MaxAccuracyBettingStrategy(BettingStrategy):
    @staticmethod
    def calculate_direction(market_p_yes: float, estimate_p_yes: float) -> bool:
        # If estimate_p_yes >= market.current_p_yes, then bet TRUE, else bet FALSE.
        # This is equivalent to saying EXPECTED_VALUE = (estimate_p_yes * num_tokens_obtained_by_betting_yes) -
        # ((1 - estimate_p_yes) * num_tokens_obtained_by_betting_no) >= 0
        return estimate_p_yes >= market_p_yes

    def calculate_bet_amount_and_direction(
        self, answer: ProbabilisticAnswer, market: AgentMarket
    ) -> TokenAmountAndDirection:
        bet_amount = (
            market.get_tiny_bet_amount().amount
            if self.bet_amount is None
            else self.bet_amount
        )
        direction = self.calculate_direction(market.current_p_yes, answer.p_yes)
        return TokenAmountAndDirection(
            amount=bet_amount,
            currency=market.currency,
            direction=direction,
        )


class KellyBettingStrategy(BettingStrategy):
    bet_amount: float

    def __init__(self, bet_amount: float = 10):
        # We add a new default here because it represents an upper bound.
        super().__init__(bet_amount=bet_amount)

    def calculate_bet_amount_and_direction(
        self, answer: ProbabilisticAnswer, market: AgentMarket
    ) -> TokenAmountAndDirection:
        kelly_bet = get_kelly_bet(
            self.bet_amount, market.current_p_yes, answer.p_yes, answer.confidence
        )
        return TokenAmountAndDirection(
            amount=kelly_bet.size,
            currency=market.currency,
            direction=kelly_bet.direction,
        )
