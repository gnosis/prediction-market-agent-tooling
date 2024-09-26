from abc import ABC, abstractmethod

import numpy as np
from scipy.optimize import bisect

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
        kelly_bet = (
            get_kelly_bet_full(
                yes_outcome_pool_size=outcome_token_pool[
                    market.get_outcome_str_from_bool(True)
                ],
                no_outcome_pool_size=outcome_token_pool[
                    market.get_outcome_str_from_bool(False)
                ],
                estimated_p_yes=answer.p_yes,
                max_bet=adjusted_bet_amount,
                confidence=answer.confidence,
            )
            if market.has_token_pool()
            else get_kelly_bet_simplified(
                adjusted_bet_amount,
                market.current_p_yes,
                answer.p_yes,
                answer.confidence,
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


class KellyMaxSlippageBettingStrategy(KellyBettingStrategy):
    def __init__(self, max_slippage: float, max_bet_amount: float):
        self.max_slippage = max_slippage
        super().__init__(max_bet_amount=max_bet_amount)

    def calc_bet_for_slippage(
        self, buy_direction: bool, bet_amount: float, yes: float, no: float, fee: float
    ) -> float:
        if buy_direction:
            r_a = yes
            r_b = no
        else:
            r_a = no
            r_b = yes

        p_a = r_b / (r_a + r_b)
        n_a = bet_amount * (r_a + r_b) / (2 * r_b)
        n_swap = r_a - ((r_a * r_b) / (r_b + ((bet_amount * (r_b + r_a)) / (2 * r_a))))
        n_r = n_a + n_swap

        p_a_new = bet_amount / n_r
        new_bet_amount = p_a * (self.max_slippage + 1) * n_r
        print(
            f" p_a {p_a} n_swap {n_swap} p_a_new {p_a_new} new_bet_amount {new_bet_amount}"
        )
        return new_bet_amount

    def calc_slippage(
        self, buy_direction: bool, bet_amount: float, yes: float, no: float, fee: float
    ):
        total_outcome_tokens = yes + no
        expected_price = (
            no / total_outcome_tokens if buy_direction else yes / total_outcome_tokens
        )
        # expected_tokens_bought = bet_amount / initial_price

        try:
            tokens_bought = get_buy_outcome_token_amount(
                bet_amount, buy_direction, yes, no, fee
            )

        except Exception as e:
            print("Error,", e)
            return 1

        actual_price = bet_amount / tokens_bought
        s = (actual_price - expected_price) / expected_price
        return s

    def calculate_slippage_for_bet_amount(
        self, market: AgentMarket, kelly_bet: SimpleBet, fee: float
    ):
        yes_outcome_pool_size = market.outcome_token_pool[
            market.get_outcome_str_from_bool(True)
        ]
        no_outcome_pool_size = market.outcome_token_pool[
            market.get_outcome_str_from_bool(False)
        ]

        # slippage for (100)
        slippage_50 = self.calc_slippage(
            kelly_bet.direction, 50, yes_outcome_pool_size, no_outcome_pool_size, fee
        )

        def slippage_diff(b: xDai) -> float:
            actual_slippage = self.calc_slippage(
                kelly_bet.direction, b, yes_outcome_pool_size, no_outcome_pool_size, fee
            )
            # translate in y
            return actual_slippage - self.max_slippage - slippage_50

        # ToDo - Try minimize_scalar, bisect
        #  https://docs.scipy.org/doc/scipy/reference/generated/scipy.optimize.minimize_scalar.html#minimize-scalar
        try:
            # optimized_bet_amount = newton(
            #     slippage_diff, self.max_bet_amount, maxiter=1000
            # )
            # We use max(pool_tokens) to find a large value of slippage if required.
            optimized_bet_amount = bisect(slippage_diff, 1e-12, 100, rtol=1e-6)

            # other_amount = root_scalar(
            #     slippage_diff, bracket=[1e-18, self.max_bet_amount]
            # )
            # optimized_bet_amount = other_amount.root
            # result = root_scalar(
            #     f, method="brentq", bracket=[1e-18, self.max_bet_amount]
            # )
            # optimized_bet_amount = result.root
        except Exception as e:
            print("Could not converge. ", e)
            return kelly_bet.size
        return optimized_bet_amount

    def calculate_trades(
        self,
        existing_position: Position | None,
        answer: ProbabilisticAnswer,
        market: AgentMarket,
    ) -> list[Trade]:
        adjusted_bet_amount = self.adjust_bet_amount(existing_position, market)
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
                max_bet=adjusted_bet_amount,
                confidence=answer.confidence,
            )
            if market.has_token_pool()
            else get_kelly_bet_simplified(
                adjusted_bet_amount,
                market.current_p_yes,
                answer.p_yes,
                answer.confidence,
            )
        )

        # Adjust amount
        # max_slippage_bet_amount = self.calculate_slippage_for_bet_amount(
        #    market, kelly_bet, 0
        # )
        new_bet_amount = self.calc_bet_for_slippage(
            kelly_bet.direction,
        )

        kelly_bet_size = min(kelly_bet.size, max_slippage_bet_amount)
        # check slippage
        slippage_num = self.calc_slippage(
            kelly_bet.direction,
            max_slippage_bet_amount,
            market.outcome_token_pool["Yes"],
            market.outcome_token_pool["No"],
            0,
        )
        print(f"slippage calc {slippage_num}")
        if not np.isclose(
            slippage_num, self.max_slippage, atol=self.max_slippage / 100
        ):
            print("Slippage wrong")
            kelly_bet_size = kelly_bet.size

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

    def __repr__(self) -> str:
        return super().__repr__() + f"(max_slippage={self.max_slippage})"


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
