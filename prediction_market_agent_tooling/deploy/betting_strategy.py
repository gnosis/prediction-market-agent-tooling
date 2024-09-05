from abc import ABC, abstractmethod
from enum import Enum

from pydantic import BaseModel

from prediction_market_agent_tooling.markets.agent_market import AgentMarket
from prediction_market_agent_tooling.markets.data_models import (
    ProbabilisticAnswer,
    Position,
    TokenAmount,
)
from prediction_market_agent_tooling.markets.omen.data_models import (
    OMEN_TRUE_OUTCOME,
    OMEN_FALSE_OUTCOME,
    get_boolean_outcome,
)
from prediction_market_agent_tooling.tools.betting_strategies.kelly_criterion import (
    get_kelly_bet,
)


class TradeType(str, Enum):
    SELL = "sell"
    BUY = "buy"


class Trade(BaseModel):
    trade_type: TradeType
    outcome: bool
    amount: TokenAmount


class BettingStrategy(ABC):
    @staticmethod
    def build_trades(
        existing_position: Position | None, target_position: Position
    ) -> list[Trade]:
        trades = []

        # ToDo - make market-agnostic
        outcomes = [OMEN_TRUE_OUTCOME, OMEN_FALSE_OUTCOME]
        for outcome in outcomes:
            outcome_bool = get_boolean_outcome(outcome)
            prev_amount: TokenAmount = (
                existing_position.amounts[outcome] if existing_position else 0
            )
            new_amount: TokenAmount = target_position.amounts[outcome]

            if prev_amount.currency != new_amount.currency:
                raise ValueError("Cannot handle positions with different currencies")
            diff_amount = prev_amount.amount - new_amount.amount
            if diff_amount == 0:
                continue
            trade_type = TradeType.SELL if diff_amount < 0 else TradeType.BUY
            trade = Trade(
                amount=TokenAmount(amount=diff_amount, currency=prev_amount.currency),
                outcome=outcome_bool,
                trade_type=trade_type,
            )

            trades.append(trade)

        return trades

    @abstractmethod
    def calculate_target_position(
        self, answer: ProbabilisticAnswer, market: AgentMarket
    ) -> Position:
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

    def calculate_target_position(
        self, answer: ProbabilisticAnswer, market: AgentMarket
    ) -> Position:
        bet_amount = (
            market.get_tiny_bet_amount().amount
            if self.bet_amount is None
            else self.bet_amount
        )
        direction = self.calculate_direction(market.current_p_yes, answer.p_yes)

        amounts = {
            direction: TokenAmount(
                amount=bet_amount,
                currency=market.currency,
            ),
            not direction: TokenAmount(amount=0, currency=market.currency),
        }
        target_position = Position(market_id=market.id, amounts=amounts)
        return target_position


class KellyBettingStrategy(BettingStrategy):
    def __init__(self, max_bet_amount: float = 10):
        self.max_bet_amount = max_bet_amount

    def calculate_target_position(
        self, answer: ProbabilisticAnswer, market: AgentMarket
    ) -> Position:
        kelly_bet = get_kelly_bet(
            self.max_bet_amount, market.current_p_yes, answer.p_yes, answer.confidence
        )

        amounts = {
            kelly_bet.direction: TokenAmount(
                amount=kelly_bet.size, currency=market.currency
            ),
            not kelly_bet.direction: TokenAmount(amount=0, currency=market.currency),
        }
        target_position = Position(market_id=market.id, amounts=amounts)
        return target_position

    # def calculate_bet_amount_and_direction(
    #     self, answer: ProbabilisticAnswer, market: AgentMarket
    # ) -> TokenAmountAndDirection:
    #     kelly_bet = get_kelly_bet(
    #         self.max_bet_amount, market.current_p_yes, answer.p_yes, answer.confidence
    #     )
    #     return TokenAmountAndDirection(
    #         amount=kelly_bet.size,
    #         currency=market.currency,
    #         direction=kelly_bet.direction,
    #     )
