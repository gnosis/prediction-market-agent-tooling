from abc import ABC, abstractmethod

from prediction_market_agent_tooling.deploy.agent import Answer
from prediction_market_agent_tooling.markets.agent_market import AgentMarket
from prediction_market_agent_tooling.markets.data_models import (
    TokenAmount,
    KellyBet,
    Currency,
    BetAmount,
)
from prediction_market_agent_tooling.tools.betting_strategies.kelly_criterion import (
    get_kelly_bet,
)


class BettingStrategy(ABC):
    @abstractmethod
    def calculate_bet_amount_and_direction(
        self, answer: Answer, market: AgentMarket
    ) -> KellyBet:
        pass


class TinyBetBettingStrategy(BettingStrategy):
    max_bet: TokenAmount = BetAmount(amount=0.00001, currency=Currency.xDai)

    def calculate_bet_amount_and_direction(
        self, answer: Answer, market: AgentMarket
    ) -> KellyBet:
        return KellyBet(size=self.max_bet.amount, direction=answer.decision)


class KellyBettingStrategy(BettingStrategy):
    max_bet: TokenAmount = TokenAmount(amount=10, currency="xDai")

    def calculate_bet_amount_and_direction(
        self, answer: Answer, market: AgentMarket
    ) -> KellyBet:
        kelly_bet = get_kelly_bet(
            self.max_bet.amount, market.current_p_yes, answer.p_yes, answer.confidence
        )
        return kelly_bet
