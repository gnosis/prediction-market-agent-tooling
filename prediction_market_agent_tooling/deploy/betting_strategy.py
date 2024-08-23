from abc import ABC, abstractmethod
from typing import TypeVar

from prediction_market_agent_tooling.markets.agent_market import AgentMarket
from prediction_market_agent_tooling.markets.data_models import (
    ProbabilisticAnswer,
    TokenAmountAndDirection,
)
from prediction_market_agent_tooling.tools.betting_strategies.kelly_criterion import (
    get_kelly_bet,
)

T = TypeVar(
    "T"
)  # Not possible to use bound due to OmenMarket and ManifoldMarket not sharing a base class


class BettingStrategy(ABC):
    @abstractmethod
    def calculate_bet_amount_and_direction(
        self, answer: ProbabilisticAnswer, market: AgentMarket
    ) -> TokenAmountAndDirection:
        pass


class MaxAccuracyBettingStrategy(BettingStrategy):
    @staticmethod
    def calculate_direction(market_p_yes: float, estimate_p_yes: float) -> bool:
        # If estimate_p_yes >= market.current_p_yes, then bet YES, else bet FALSE.
        # This is equivalent to saying EXPECTED_VALUE = (estimate_p_yes * num_tokens_obtained_by_betting_yes) -
        # ((1 - estimate_p_yes) * num_tokens_obtained_by_betting_no) >= 0
        return estimate_p_yes >= market_p_yes

    def calculate_bet_amount_and_direction(
        self, answer: ProbabilisticAnswer, market: AgentMarket
    ) -> TokenAmountAndDirection:
        bet_amount = market.get_tiny_bet_amount().amount
        direction = self.calculate_direction(market.current_p_yes, answer.p_yes)
        return TokenAmountAndDirection(
            amount=bet_amount,
            currency=market.currency,
            direction=direction,
        )


class KellyBettingStrategy(BettingStrategy):
    @staticmethod
    def get_max_bet_amount_for_market() -> float:
        # No difference between markets.
        return 10  # Mana or xDAI

    def calculate_bet_amount_and_direction(
        self, answer: ProbabilisticAnswer, market: AgentMarket
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
