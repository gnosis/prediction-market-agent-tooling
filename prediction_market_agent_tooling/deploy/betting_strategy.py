from abc import ABC, abstractmethod

from prediction_market_agent_tooling.markets.agent_market import AgentMarket
from prediction_market_agent_tooling.markets.data_models import (
    ProbabilisticAnswer,
    TokenAmountAndDirection,
)
from prediction_market_agent_tooling.markets.omen.data_models import OMEN_TRUE_OUTCOME
from prediction_market_agent_tooling.tools.betting_strategies.kelly_criterion import (
    get_kelly_bet_full,
    get_kelly_bet_simplified,
)
from prediction_market_agent_tooling.tools.utils import check_not_none


class BettingStrategy(ABC):
    @abstractmethod
    def calculate_bet_amount_and_direction(
        self, answer: ProbabilisticAnswer, market: AgentMarket
    ) -> TokenAmountAndDirection:
        pass


class MaxAccuracyBettingStrategy(BettingStrategy):
    def __init__(self, bet_amount: float | None = None):
        self.bet_amount = bet_amount

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
    def __init__(self, max_bet_amount: float = 10):
        self.max_bet_amount = max_bet_amount

    def calculate_bet_amount_and_direction(
        self, answer: ProbabilisticAnswer, market: AgentMarket
    ) -> TokenAmountAndDirection:
        # TODO use market.get_outcome_str_from_bool after https://github.com/gnosis/prediction-market-agent-tooling/pull/387 merges
        kelly_bet = (
            get_kelly_bet_full(
                yes_outcome_pool_size=check_not_none(market.outcome_token_pool)[
                    OMEN_TRUE_OUTCOME
                ],
                no_outcome_pool_size=check_not_none(market.outcome_token_pool)[
                    OMEN_TRUE_OUTCOME
                ],
                estimated_p_yes=answer.p_yes,
                max_bet=self.max_bet_amount,
                confidence=answer.confidence,
            )
            if market.has_token_pool()
            else get_kelly_bet_simplified(
                self.max_bet_amount,
                market.current_p_yes,
                answer.p_yes,
                answer.confidence,
            )
        )
        return TokenAmountAndDirection(
            amount=kelly_bet.size,
            currency=market.currency,
            direction=kelly_bet.direction,
        )
