from abc import ABC, abstractmethod, ABCMeta

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


class FixedBetBettingStrategy(BettingStrategy, metaclass=ABCMeta):
    @property
    @abstractmethod
    def bet_amount(self) -> float:
        pass

    def calculate_bet_amount_and_direction(
        self, answer: Answer, market: AgentMarket
    ) -> TokenAmountAndDirection:
        return TokenAmountAndDirection(
            amount=self.bet_amount,
            currency=market.currency,
            direction=answer.decision,
        )


class ManifoldFixedBetBettingStrategy(FixedBetBettingStrategy):
    @property
    def bet_amount(self) -> float:
        return 1.0  # Mana


class OmenFixedBetBettingStrategy(FixedBetBettingStrategy):
    @property
    def bet_amount(self) -> float:
        return 0.00001  # xDAI


# ToDo - Make this abstract
class KellyBettingStrategy(BettingStrategy, metaclass=ABCMeta):
    @property
    @abstractmethod
    def max_bet_amount(self) -> float:
        pass

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
    @property
    def max_bet_amount(self) -> float:
        return 10  # xDAI


class ManifoldKellyBettingStrategy(KellyBettingStrategy):
    @property
    def max_bet_amount(self) -> float:
        return 10  # Mana
