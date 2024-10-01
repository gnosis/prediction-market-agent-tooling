from abc import ABC, abstractmethod

import numpy as np
from loguru import logger
from scipy.optimize import minimize_scalar

from prediction_market_agent_tooling.gtypes import xDai
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
from prediction_market_agent_tooling.markets.omen.omen import (
    get_buy_outcome_token_amount,
)
from prediction_market_agent_tooling.tools.betting_strategies.kelly_criterion import (
    get_kelly_bet_full,
    get_kelly_bet_simplified,
)
from prediction_market_agent_tooling.tools.betting_strategies.utils import SimpleBet
from prediction_market_agent_tooling.tools.utils import check_not_none


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
            diff_amount = new_amount.amount - prev_amount.amount
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
    def __init__(self, bet_amount: float):
        self.bet_amount = bet_amount

    def calculate_trades(
        self,
        existing_position: Position | None,
        answer: ProbabilisticAnswer,
        market: AgentMarket,
    ) -> list[Trade]:
        direction = self.calculate_direction(market.current_p_yes, answer.p_yes)

        amounts = {
            market.get_outcome_str_from_bool(direction): TokenAmount(
                amount=self.bet_amount,
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

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}(bet_amount={self.bet_amount})"


class MaxExpectedValueBettingStrategy(MaxAccuracyBettingStrategy):
    @staticmethod
    def calculate_direction(market_p_yes: float, estimate_p_yes: float) -> bool:
        # If estimate_p_yes >= market.current_p_yes, then bet TRUE, else bet FALSE.
        # This is equivalent to saying EXPECTED_VALUE = (estimate_p_yes * num_tokens_obtained_by_betting_yes) -
        # ((1 - estimate_p_yes) * num_tokens_obtained_by_betting_no) >= 0
        return estimate_p_yes >= market_p_yes


class KellyBettingStrategy(BettingStrategy):
    def __init__(self, max_bet_amount: float, max_price_impact: float | None = None):
        self.max_bet_amount = max_bet_amount
        self.max_price_impact = max_price_impact

    def _check_price_impact_ok_else_log(
        self, buy_direction: bool, bet_size: float, market: AgentMarket
    ) -> None:
        price_impact = self.calculate_price_impact_for_bet_amount(
            buy_direction,
            bet_size,
            market.outcome_token_pool["Yes"],
            market.outcome_token_pool["No"],
            0,
        )

        if price_impact > self.max_price_impact and not np.isclose(
            price_impact, self.max_price_impact, atol=self.max_price_impact * 0.01
        ):
            logger.info(
                f"Price impact {price_impact} deviates too much from self.max_price_impact {self.max_price_impact}, market_id {market.id}"
            )

    def calculate_trades(
        self,
        existing_position: Position | None,
        answer: ProbabilisticAnswer,
        market: AgentMarket,
    ) -> list[Trade]:
        outcome_token_pool = check_not_none(market.outcome_token_pool)
        kelly_bet = (
            get_kelly_bet_full(
                yes_outcome_pool_size=outcome_token_pool[
                    market.get_outcome_str_from_bool(True)
                ],
                no_outcome_pool_size=outcome_token_pool[
                    market.get_outcome_str_from_bool(False)
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

        kelly_bet_size = kelly_bet.size
        if self.max_price_impact:
            # Adjust amount
            max_slippage_bet_amount = self.calculate_bet_amount_for_price_impact(
                market, kelly_bet, 0
            )

            # We just don't want Kelly size to extrapolate price_impact - hence we take the min.
            kelly_bet_size = min(kelly_bet.size, max_slippage_bet_amount)

            self._check_price_impact_ok_else_log(
                kelly_bet.direction, kelly_bet_size, market
            )

        amounts = {
            market.get_outcome_str_from_bool(kelly_bet.direction): TokenAmount(
                amount=kelly_bet_size, currency=market.currency
            ),
        }
        target_position = Position(market_id=market.id, amounts=amounts)
        trades = self._build_rebalance_trades_from_positions(
            existing_position, target_position, market=market
        )
        return trades

    def calculate_price_impact_for_bet_amount(
        self, buy_direction: bool, bet_amount: float, yes: float, no: float, fee: float
    ) -> float:
        total_outcome_tokens = yes + no
        expected_price = (
            no / total_outcome_tokens if buy_direction else yes / total_outcome_tokens
        )

        tokens_to_buy = get_buy_outcome_token_amount(
            bet_amount, buy_direction, yes, no, fee
        )

        actual_price = bet_amount / tokens_to_buy
        # price_impact should always be > 0
        price_impact = (actual_price - expected_price) / expected_price
        return price_impact

    def calculate_bet_amount_for_price_impact(
        self, market: AgentMarket, kelly_bet: SimpleBet, fee: float
    ) -> float:
        def calculate_price_impact_deviation_from_target_price_impact(b: xDai) -> float:
            price_impact = self.calculate_price_impact_for_bet_amount(
                kelly_bet.direction, b, yes_outcome_pool_size, no_outcome_pool_size, fee
            )
            # We return abs for the algorithm to converge to 0 instead of the min (and possibly negative) value.
            return abs(price_impact - self.max_price_impact)

        yes_outcome_pool_size = market.outcome_token_pool[
            market.get_outcome_str_from_bool(True)
        ]
        no_outcome_pool_size = market.outcome_token_pool[
            market.get_outcome_str_from_bool(False)
        ]

        optimized_bet_amount = minimize_scalar(
            calculate_price_impact_deviation_from_target_price_impact,
            bounds=(min(yes_outcome_pool_size, no_outcome_pool_size) / 1000, 1000),
            method="bounded",
            tol=1e-11,
            options={"maxiter": 10000},
        )
        return optimized_bet_amount.x

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}(max_bet_amount={self.max_bet_amount}, max_price_impact={self.max_price_impact})"


class MaxAccuracyWithKellyScaledBetsStrategy(BettingStrategy):
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
        outcome_token_pool = check_not_none(market.outcome_token_pool)

        # Fixed direction of bet, only use Kelly to adjust the bet size based on market's outcome pool size.
        estimated_p_yes = float(answer.p_yes > 0.5)
        confidence = 1.0

        kelly_bet = (
            get_kelly_bet_full(
                yes_outcome_pool_size=outcome_token_pool[
                    market.get_outcome_str_from_bool(True)
                ],
                no_outcome_pool_size=outcome_token_pool[
                    market.get_outcome_str_from_bool(False)
                ],
                estimated_p_yes=estimated_p_yes,
                max_bet=adjusted_bet_amount,
                confidence=confidence,
            )
            if market.has_token_pool()
            else get_kelly_bet_simplified(
                adjusted_bet_amount,
                market.current_p_yes,
                estimated_p_yes,
                confidence,
            )
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

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}(max_bet_amount={self.max_bet_amount})"
