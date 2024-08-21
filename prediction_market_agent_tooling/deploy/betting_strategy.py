from abc import ABC, ABCMeta, abstractmethod

from prediction_market_agent_tooling.markets.agent_market import AgentMarket
from prediction_market_agent_tooling.markets.data_models import (
    Answer,
    Currency,
    TokenAmount,
    TokenAmountAndDirection,
)
from prediction_market_agent_tooling.markets.manifold.manifold import (
    ManifoldAgentMarket,
)
from prediction_market_agent_tooling.markets.omen.omen import OmenAgentMarket
from prediction_market_agent_tooling.tools.betting_strategies.kelly_criterion import (
    get_kelly_bet,
)


class BettingStrategy(ABC):
    @abstractmethod
    def calculate_bet_amount_and_direction(
        self, answer: Answer, market: AgentMarket
    ) -> TokenAmountAndDirection:
        pass


MINIMUM_BET_OMEN = TokenAmount(amount=0.00001, currency=Currency.xDai)
MINIMUM_BET_MANIFOLD = TokenAmount(amount=1, currency=Currency.Mana)


class FixedBetBettingStrategy(BettingStrategy, metaclass=ABCMeta):
    def get_bet_amount_for_market(self, market: AgentMarket) -> float:
        if isinstance(market, ManifoldAgentMarket):
            return MINIMUM_BET_MANIFOLD.amount
        elif isinstance(market, OmenAgentMarket):
            return MINIMUM_BET_OMEN.amount
        else:
            raise ValueError(f"Cannot process market: {market}")

    def calculate_bet_amount_and_direction(
        self, answer: Answer, market: AgentMarket
    ) -> TokenAmountAndDirection:
        bet_amount = self.get_bet_amount_for_market(market)
        return TokenAmountAndDirection(
            amount=bet_amount,
            currency=market.currency,
            direction=answer.decision,
        )


class KellyBettingStrategy(BettingStrategy, metaclass=ABCMeta):
    def get_max_bet_amount_for_market(self) -> float:
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
