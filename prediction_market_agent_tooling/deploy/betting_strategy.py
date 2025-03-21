from abc import ABC, abstractmethod

from scipy.optimize import minimize_scalar

from prediction_market_agent_tooling.gtypes import USD, OutcomeToken, Token
from prediction_market_agent_tooling.loggers import logger
from prediction_market_agent_tooling.markets.agent_market import AgentMarket, MarketFees
from prediction_market_agent_tooling.markets.data_models import (
    ExistingPosition,
    Position,
    ProbabilisticAnswer,
    Trade,
    TradeType,
)
from prediction_market_agent_tooling.markets.omen.omen import (
    get_buy_outcome_token_amount,
)
from prediction_market_agent_tooling.tools.betting_strategies.kelly_criterion import (
    get_kelly_bet_full,
)
from prediction_market_agent_tooling.tools.betting_strategies.utils import SimpleBet
from prediction_market_agent_tooling.tools.utils import check_not_none


class GuaranteedLossError(RuntimeError):
    pass


class BettingStrategy(ABC):
    @abstractmethod
    def calculate_trades(
        self,
        existing_position: ExistingPosition | None,
        answer: ProbabilisticAnswer,
        market: AgentMarket,
    ) -> list[Trade]:
        raise NotImplementedError("Subclass should implement this.")

    @property
    @abstractmethod
    def maximum_possible_bet_amount(self) -> USD:
        raise NotImplementedError("Subclass should implement this.")

    def build_zero_usd_amount(self) -> USD:
        return USD(0)

    @staticmethod
    def assert_buy_trade_wont_be_guaranteed_loss(
        market: AgentMarket, trades: list[Trade]
    ) -> None:
        for trade in trades:
            if trade.trade_type == TradeType.BUY:
                outcome_tokens_to_get = market.get_buy_token_amount(
                    trade.amount, trade.outcome
                )
                outcome_tokens_to_get_in_usd = market.get_token_in_usd(
                    outcome_tokens_to_get.as_token
                )
                if outcome_tokens_to_get_in_usd <= trade.amount:
                    raise GuaranteedLossError(
                        f"Trade {trade=} would result in guaranteed loss by getting only {outcome_tokens_to_get=}."
                    )

    @staticmethod
    def check_trades(market: AgentMarket, trades: list[Trade]) -> None:
        BettingStrategy.assert_buy_trade_wont_be_guaranteed_loss(market, trades)

    def _build_rebalance_trades_from_positions(
        self,
        existing_position: ExistingPosition | None,
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
        for outcome_bool in [True, False]:
            outcome = market.get_outcome_str_from_bool(outcome_bool)
            prev_amount = (
                existing_position.amounts_current[outcome]
                if existing_position and outcome in existing_position.amounts_current
                else self.build_zero_usd_amount()
            )
            new_amount = target_position.amounts_current.get(
                outcome, self.build_zero_usd_amount()
            )
            diff_amount = new_amount - prev_amount
            if diff_amount == 0:
                continue
            trade_type = TradeType.SELL if diff_amount < 0 else TradeType.BUY
            trade = Trade(
                amount=abs(diff_amount),
                outcome=outcome_bool,
                trade_type=trade_type,
            )

            trades.append(trade)

        # Sort inplace with SELL last
        trades.sort(key=lambda t: t.trade_type == TradeType.SELL)

        # Run some sanity checks to not place unreasonable bets.
        BettingStrategy.check_trades(market, trades)

        return trades


class MaxAccuracyBettingStrategy(BettingStrategy):
    def __init__(self, bet_amount: USD):
        self.bet_amount = bet_amount

    @property
    def maximum_possible_bet_amount(self) -> USD:
        return self.bet_amount

    def calculate_trades(
        self,
        existing_position: ExistingPosition | None,
        answer: ProbabilisticAnswer,
        market: AgentMarket,
    ) -> list[Trade]:
        direction = self.calculate_direction(market.current_p_yes, answer.p_yes)

        amounts = {
            market.get_outcome_str_from_bool(direction): self.bet_amount,
        }
        target_position = Position(market_id=market.id, amounts_current=amounts)
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
    def __init__(self, max_bet_amount: USD, max_price_impact: float | None = None):
        self.max_bet_amount = max_bet_amount
        self.max_price_impact = max_price_impact

    @property
    def maximum_possible_bet_amount(self) -> USD:
        return self.max_bet_amount

    def calculate_trades(
        self,
        existing_position: ExistingPosition | None,
        answer: ProbabilisticAnswer,
        market: AgentMarket,
    ) -> list[Trade]:
        outcome_token_pool = check_not_none(market.outcome_token_pool)
        kelly_bet = get_kelly_bet_full(
            yes_outcome_pool_size=outcome_token_pool[
                market.get_outcome_str_from_bool(True)
            ],
            no_outcome_pool_size=outcome_token_pool[
                market.get_outcome_str_from_bool(False)
            ],
            estimated_p_yes=answer.p_yes,
            max_bet=market.get_usd_in_token(self.max_bet_amount),
            confidence=answer.confidence,
            fees=market.fees,
        )

        kelly_bet_size = kelly_bet.size
        if self.max_price_impact:
            # Adjust amount
            max_price_impact_bet_amount = self.calculate_bet_amount_for_price_impact(
                market, kelly_bet
            )

            # We just don't want Kelly size to extrapolate price_impact - hence we take the min.
            kelly_bet_size = min(kelly_bet.size, max_price_impact_bet_amount)

        amounts = {
            market.get_outcome_str_from_bool(
                kelly_bet.direction
            ): market.get_token_in_usd(kelly_bet_size),
        }
        target_position = Position(market_id=market.id, amounts_current=amounts)
        trades = self._build_rebalance_trades_from_positions(
            existing_position, target_position, market=market
        )
        return trades

    def calculate_price_impact_for_bet_amount(
        self,
        buy_direction: bool,
        bet_amount: Token,
        yes: OutcomeToken,
        no: OutcomeToken,
        fees: MarketFees,
    ) -> float:
        total_outcome_tokens = yes + no
        expected_price = (
            no / total_outcome_tokens if buy_direction else yes / total_outcome_tokens
        )

        tokens_to_buy = get_buy_outcome_token_amount(
            bet_amount, buy_direction, yes, no, fees
        )

        actual_price = bet_amount.value / tokens_to_buy.value
        # price_impact should always be > 0
        price_impact = (actual_price - expected_price) / expected_price
        return price_impact

    def calculate_bet_amount_for_price_impact(
        self,
        market: AgentMarket,
        kelly_bet: SimpleBet,
    ) -> Token:
        def calculate_price_impact_deviation_from_target_price_impact(
            bet_amount_usd: float,  # Needs to be float because it's used in minimize_scalar internally.
        ) -> float:
            price_impact = self.calculate_price_impact_for_bet_amount(
                kelly_bet.direction,
                market.get_usd_in_token(USD(bet_amount_usd)),
                yes_outcome_pool_size,
                no_outcome_pool_size,
                market.fees,
            )
            # We return abs for the algorithm to converge to 0 instead of the min (and possibly negative) value.

            max_price_impact = check_not_none(self.max_price_impact)
            return abs(price_impact - max_price_impact)

        if not market.outcome_token_pool:
            logger.warning(
                "Market outcome_token_pool is None, cannot calculate bet amount"
            )
            return kelly_bet.size

        yes_outcome_pool_size = market.outcome_token_pool[
            market.get_outcome_str_from_bool(True)
        ]
        no_outcome_pool_size = market.outcome_token_pool[
            market.get_outcome_str_from_bool(False)
        ]

        # The bounds below have been found to work heuristically.
        optimized_bet_amount = minimize_scalar(
            calculate_price_impact_deviation_from_target_price_impact,
            bounds=(0, 1000 * (yes_outcome_pool_size + no_outcome_pool_size).value),
            method="bounded",
            tol=1e-11,
            options={"maxiter": 10000},
        )
        return Token(optimized_bet_amount.x)

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}(max_bet_amount={self.max_bet_amount}, max_price_impact={self.max_price_impact})"


class MaxAccuracyWithKellyScaledBetsStrategy(BettingStrategy):
    def __init__(self, max_bet_amount: USD):
        self.max_bet_amount = max_bet_amount

    @property
    def maximum_possible_bet_amount(self) -> USD:
        return self.max_bet_amount

    def adjust_bet_amount(
        self, existing_position: ExistingPosition | None, market: AgentMarket
    ) -> USD:
        existing_position_total_amount = (
            existing_position.total_amount_current if existing_position else USD(0)
        )
        return self.max_bet_amount + existing_position_total_amount

    def calculate_trades(
        self,
        existing_position: ExistingPosition | None,
        answer: ProbabilisticAnswer,
        market: AgentMarket,
    ) -> list[Trade]:
        adjusted_bet_amount_usd = self.adjust_bet_amount(existing_position, market)
        adjusted_bet_amount_token = market.get_usd_in_token(adjusted_bet_amount_usd)
        outcome_token_pool = check_not_none(market.outcome_token_pool)

        # Fixed direction of bet, only use Kelly to adjust the bet size based on market's outcome pool size.
        estimated_p_yes = float(answer.p_yes > 0.5)
        confidence = 1.0

        kelly_bet = get_kelly_bet_full(
            yes_outcome_pool_size=outcome_token_pool[
                market.get_outcome_str_from_bool(True)
            ],
            no_outcome_pool_size=outcome_token_pool[
                market.get_outcome_str_from_bool(False)
            ],
            estimated_p_yes=estimated_p_yes,
            max_bet=adjusted_bet_amount_token,
            confidence=confidence,
            fees=market.fees,
        )
        kelly_bet_size_usd = market.get_token_in_usd(kelly_bet.size)

        amounts = {
            market.get_outcome_str_from_bool(kelly_bet.direction): kelly_bet_size_usd,
        }
        target_position = Position(market_id=market.id, amounts_current=amounts)
        trades = self._build_rebalance_trades_from_positions(
            existing_position, target_position, market=market
        )
        return trades

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}(max_bet_amount={self.max_bet_amount})"
