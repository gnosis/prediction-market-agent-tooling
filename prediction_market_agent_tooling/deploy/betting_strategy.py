from abc import ABC, abstractmethod

from prediction_market_agent_tooling.markets.agent_market import AgentMarket
from prediction_market_agent_tooling.markets.data_models import (
    Currency,
    Position,
    ProbabilisticAnswer,
    TokenAmount,
    Trade,
    TradeType,
)
from prediction_market_agent_tooling.markets.omen.data_models import get_boolean_outcome
from prediction_market_agent_tooling.tools.betting_strategies.kelly_criterion import (
    get_kelly_bet,
)


class BettingStrategy(ABC):
    @abstractmethod
    def calculate_trades(
        self,
        existing_position: Position | None,
        answer: ProbabilisticAnswer,
        market: AgentMarket,
    ) -> list[Trade]:
        pass

    def build_zero_token_amount(self, currency: Currency) -> TokenAmount:
        return TokenAmount(amount=0, currency=currency)

    @abstractmethod
    def adjust_bet_amount(
        self, existing_position: Position | None, market: AgentMarket
    ) -> float:
        pass

    @staticmethod
    def assert_trades_currency_match_markets(
        market: AgentMarket, trades: list[Trade]
    ) -> None:
        currencies_match = all([t.amount.currency == market.currency for t in trades])
        if not currencies_match:
            raise ValueError(
                "Cannot handle trades with currencies that deviate from market's currency"
            )

    def _build_rebalance_trades_from_positions(
        self,
        existing_position: Position | None,
        target_position: Position,
        market: AgentMarket,
    ) -> list[Trade]:
        """
        This helper method builds trades by rebalancing token allocations to each outcome.
        For example, if we have an existing position with 10 tokens in outcome 0 and 5 in outcome 1,
        and our target position is 20 tokens in outcome 0 and 0 in outcome 1, we would return these trades:
        trades = [
            Trade(outcome=0, amount=10, trade_type=TradeType.BUY),
            Trade(outcome=1, amount=5, trade_type=TradeType.SELL)
        ]
        Note that we order the trades to first buy then sell, in order to minimally tilt the odds so that
        sell price is higher.
        """
        trades = []
        for outcome in [
            market.get_outcome_str_from_bool(True),
            market.get_outcome_str_from_bool(False),
        ]:
            outcome_bool = get_boolean_outcome(outcome)
            prev_amount: TokenAmount = (
                existing_position.amounts[outcome]
                if existing_position and outcome in existing_position.amounts
                else self.build_zero_token_amount(currency=market.currency)
            )
            new_amount: TokenAmount = target_position.amounts.get(
                outcome, self.build_zero_token_amount(currency=market.currency)
            )

            if prev_amount.currency != new_amount.currency:
                raise ValueError("Cannot handle positions with different currencies")
            diff_amount = prev_amount.amount - new_amount.amount
            if diff_amount == 0:
                continue
            trade_type = TradeType.SELL if diff_amount < 0 else TradeType.BUY
            trade = Trade(
                amount=TokenAmount(amount=abs(diff_amount), currency=market.currency),
                outcome=outcome_bool,
                trade_type=trade_type,
            )

            trades.append(trade)

        # Sort inplace with SELL last
        trades.sort(key=lambda t: t.trade_type == TradeType.SELL)
        BettingStrategy.assert_trades_currency_match_markets(market, trades)
        return trades


class MaxAccuracyBettingStrategy(BettingStrategy):
    def adjust_bet_amount(
        self, existing_position: Position | None, market: AgentMarket
    ) -> float:
        existing_position_total_amount = (
            existing_position.total_amount.amount if existing_position else 0
        )
        bet_amount = (
            market.get_tiny_bet_amount().amount
            if self.bet_amount is None
            else self.bet_amount
        )
        return bet_amount + existing_position_total_amount

    def __init__(self, bet_amount: float | None = None):
        self.bet_amount = bet_amount

    def calculate_trades(
        self,
        existing_position: Position | None,
        answer: ProbabilisticAnswer,
        market: AgentMarket,
    ) -> list[Trade]:
        adjusted_bet_amount = self.adjust_bet_amount(existing_position, market)

        direction = self.calculate_direction(market.current_p_yes, answer.p_yes)

        amounts = {
            market.get_outcome_str_from_bool(direction): TokenAmount(
                amount=adjusted_bet_amount,
                currency=market.currency,
            ),
        }
        target_position = Position(market_id=market.id, amounts=amounts)
        trades = self._build_rebalance_trades_from_positions(
            existing_position, target_position, market=market
        )
        return trades

    @staticmethod
    def calculate_direction(market_p_yes: float, estimate_p_yes: float) -> bool:
        return estimate_p_yes >= 0.5


class MaxExpectedValueBettingStrategy(MaxAccuracyBettingStrategy):
    @staticmethod
    def calculate_direction(market_p_yes: float, estimate_p_yes: float) -> bool:
        # If estimate_p_yes >= market.current_p_yes, then bet TRUE, else bet FALSE.
        # This is equivalent to saying EXPECTED_VALUE = (estimate_p_yes * num_tokens_obtained_by_betting_yes) -
        # ((1 - estimate_p_yes) * num_tokens_obtained_by_betting_no) >= 0
        return estimate_p_yes >= market_p_yes


class KellyBettingStrategy(BettingStrategy):
    def __init__(self, max_bet_amount: float = 10):
        self.max_bet_amount = max_bet_amount

    def adjust_bet_amount(
        self, existing_position: Position | None, market: AgentMarket
    ) -> float:
        existing_position_total_amount = (
            existing_position.total_amount.amount if existing_position else 0
        )
        return self.max_bet_amount + existing_position_total_amount

    def calculate_trades(
        self,
        existing_position: Position | None,
        answer: ProbabilisticAnswer,
        market: AgentMarket,
    ) -> list[Trade]:
        adjusted_bet_amount = self.adjust_bet_amount(existing_position, market)
        kelly_bet = get_kelly_bet(
            adjusted_bet_amount,
            market.current_p_yes,
            answer.p_yes,
            answer.confidence,
        )

        amounts = {
            market.get_outcome_str_from_bool(kelly_bet.direction): TokenAmount(
                amount=kelly_bet.size, currency=market.currency
            ),
        }
        target_position = Position(market_id=market.id, amounts=amounts)
        trades = self._build_rebalance_trades_from_positions(
            existing_position, target_position, market=market
        )
        return trades
