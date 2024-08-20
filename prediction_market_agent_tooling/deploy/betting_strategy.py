from abc import ABC, abstractmethod

from prediction_market_agent_tooling.deploy.agent import Answer
from prediction_market_agent_tooling.markets.agent_market import AgentMarket
from prediction_market_agent_tooling.markets.data_models import (
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


# ToDo - Make this abstract
class FixedBetBettingStrategy(BettingStrategy):
    bet_amount: float

    def calculate_bet_amount_and_direction(
        self, answer: Answer, market: AgentMarket
    ) -> TokenAmountAndDirection:
        return TokenAmountAndDirection(
            amount=self.bet_amount,
            currency=market.currency,
            direction=answer.decision,
        )


class ManifoldFixedBetBettingStrategy(FixedBetBettingStrategy):
    bet_amount = 1.0  # 1 Mana


class OmenFixedBetBettingStrategy(FixedBetBettingStrategy):
    bet_amount = 0.00001  # xDAI


# ToDo - Make this abstract
class KellyBettingStrategy(BettingStrategy):
    max_bet_amount: float

    def calculate_bet_amount_and_direction(
        self, answer: Answer, market: AgentMarket
    ) -> TokenAmountAndDirection:
        kelly_bet = get_kelly_bet(
            self.max_bet_amount, market.current_p_yes, answer.p_yes, answer.confidence
        )
        return TokenAmountAndDirection(
            amount=kelly_bet.size,
            currency=market.currency,
            direction=kelly_bet.direction,
        )


class OmenKellyBettingStrategy(KellyBettingStrategy):
    max_bet_amount = 10  # xDAI


class ManifoldKellyBettingStrategy(KellyBettingStrategy):
    max_bet_amount = 10  # Mana
