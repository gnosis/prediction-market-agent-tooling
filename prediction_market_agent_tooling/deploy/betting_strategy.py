from abc import ABC, abstractmethod
from math import prod

from scipy.optimize import minimize_scalar

from prediction_market_agent_tooling.benchmark.utils import get_most_probable_outcome
from prediction_market_agent_tooling.deploy.constants import (
    INVALID_OUTCOME_LOWERCASE_IDENTIFIER,
)
from prediction_market_agent_tooling.gtypes import (
    USD,
    CollateralToken,
    OutcomeStr,
    OutcomeToken,
    Probability,
)
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
    get_kelly_bet_simplified,
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

    @staticmethod
    def build_zero_usd_amount() -> USD:
        return USD(0)

    @staticmethod
    def assert_buy_trade_wont_be_guaranteed_loss(
        market: AgentMarket, trades: list[Trade]
    ) -> list[Trade]:
        clean_trades = []
        for trade in trades:
            if trade.trade_type == TradeType.BUY:
                outcome_tokens_to_get = market.get_buy_token_amount(
                    trade.amount, trade.outcome
                )

                if not outcome_tokens_to_get:
                    logger.info(
                        f"Could not determine buy_token_amount for trade {trade}. Skipping trade."
                    )
                    continue

                outcome_tokens_to_get_in_usd = market.get_token_in_usd(
                    outcome_tokens_to_get.as_token
                )

                if outcome_tokens_to_get_in_usd <= trade.amount:
                    raise GuaranteedLossError(
                        f"Trade {trade=} would result in guaranteed loss by getting only {outcome_tokens_to_get=}. Halting execution."
                    )

            clean_trades.append(trade)

        return clean_trades

    @staticmethod
    def filter_trades(market: AgentMarket, trades: list[Trade]) -> list[Trade]:
        trades = BettingStrategy.assert_buy_trade_wont_be_guaranteed_loss(
            market, trades
        )
        return trades

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
        for outcome in market.outcomes:
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
                outcome=outcome,
                trade_type=trade_type,
            )

            trades.append(trade)

        # Sort inplace with SELL last
        trades.sort(key=lambda t: t.trade_type == TradeType.SELL)

        # Run some sanity checks to not place unreasonable bets.
        trades = BettingStrategy.filter_trades(market, trades)

        return trades


class MultiCategoricalMaxAccuracyBettingStrategy(BettingStrategy):
    def __init__(self, bet_amount: USD):
        self.bet_amount = bet_amount

    @property
    def maximum_possible_bet_amount(self) -> USD:
        return self.bet_amount

    @staticmethod
    def calculate_direction(
        market: AgentMarket, answer: ProbabilisticAnswer
    ) -> OutcomeStr:
        # We place a bet on the most likely outcome
        most_likely_outcome = max(
            answer.probabilities.items(),
            key=lambda item: item[1],
        )[0]
        return most_likely_outcome

    def calculate_trades(
        self,
        existing_position: ExistingPosition | None,
        answer: ProbabilisticAnswer,
        market: AgentMarket,
    ) -> list[Trade]:
        """We place bet on only one outcome."""

        outcome_to_bet_on = self.calculate_direction(market, answer)

        target_position = Position(
            market_id=market.id, amounts_current={outcome_to_bet_on: self.bet_amount}
        )
        trades = self._build_rebalance_trades_from_positions(
            existing_position=existing_position,
            target_position=target_position,
            market=market,
        )
        return trades


class MaxExpectedValueBettingStrategy(MultiCategoricalMaxAccuracyBettingStrategy):
    @staticmethod
    def calculate_direction(
        market: AgentMarket, answer: ProbabilisticAnswer
    ) -> OutcomeStr:
        """
        Returns the index of the outcome with the highest expected value.
        """
        missing_outcomes = set(market.outcomes) - set(answer.probabilities.keys())
        if missing_outcomes:
            raise ValueError(
                f"Outcomes {missing_outcomes} not found in answer probabilities {answer.probabilities}"
            )

        best_outcome = None
        best_ev = float("-inf")
        for outcome in market.outcomes:
            if market.probabilities[outcome] == Probability(0.0):
                # avoid division by 0
                continue
            ev = answer.probabilities[outcome] / market.probabilities[outcome]
            if ev > best_ev:
                best_ev = ev
                best_outcome = outcome

        if best_outcome is None:
            raise ValueError(
                "Cannot determine best outcome - all market probabilities are zero"
            )

        return best_outcome


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
        # We consider the p_yes as the direction with highest probability.
        direction = MultiCategoricalMaxAccuracyBettingStrategy.calculate_direction(
            market, answer
        )
        # We get the first direction which is != direction.
        other_direction = [i for i in market.outcomes if i != direction][0]
        if INVALID_OUTCOME_LOWERCASE_IDENTIFIER in other_direction.lower():
            raise ValueError("Invalid outcome found as opposite direction. Exitting.")

        if not market.is_binary:
            # use Kelly simple, since Kelly full only supports 2 outcomes
            kelly_bet = get_kelly_bet_simplified(
                max_bet=market.get_usd_in_token(self.max_bet_amount),
                market_p_yes=market.probabilities[direction],
                estimated_p_yes=answer.probabilities[direction],
                confidence=answer.confidence,
            )
        else:
            # We consider only binary markets, since the Kelly strategy is not yet implemented
            # for markets with more than 2 outcomes (https://github.com/gnosis/prediction-market-agent-tooling/issues/671).
            direction_to_bet_pool_size = outcome_token_pool[direction]
            other_direction_pool_size = outcome_token_pool[other_direction]
            kelly_bet = get_kelly_bet_full(
                yes_outcome_pool_size=direction_to_bet_pool_size,
                no_outcome_pool_size=other_direction_pool_size,
                estimated_p_yes=answer.probabilities[direction],
                max_bet=market.get_usd_in_token(self.max_bet_amount),
                confidence=answer.confidence,
                fees=market.fees,
            )

        kelly_bet_size = kelly_bet.size
        if self.max_price_impact:
            # Adjust amount
            max_price_impact_bet_amount = self.calculate_bet_amount_for_price_impact(
                market, kelly_bet, direction=direction
            )

            # We just don't want Kelly size to extrapolate price_impact - hence we take the min.
            kelly_bet_size = min(kelly_bet.size, max_price_impact_bet_amount)

        bet_outcome = direction if kelly_bet.direction else other_direction
        amounts = {
            bet_outcome: market.get_token_in_usd(kelly_bet_size),
        }
        target_position = Position(market_id=market.id, amounts_current=amounts)
        trades = self._build_rebalance_trades_from_positions(
            existing_position, target_position, market=market
        )
        return trades

    def get_outcome_prices_from_balances(self, balances: list[float]) -> list[float]:
        num_balances = len(balances)
        prices = []

        # Compute the product of all outcome balances except i for each i
        for i in range(num_balances):
            numerator = prod([balances[j] for j in range(num_balances) if j != i])
            prices.append(numerator)

        denominator = sum(prices)
        normalized_prices = [p / denominator for p in prices]

        return normalized_prices

    def calculate_price_impact_for_bet_amount(
        self,
        outcome_idx: int,
        bet_amount: CollateralToken,
        pool_balances: list[float],
        fees: MarketFees,
    ) -> float:
        prices = self.get_outcome_prices_from_balances(pool_balances)
        expected_price = prices[outcome_idx]

        tokens_to_buy = get_buy_outcome_token_amount(
            bet_amount, outcome_idx, [OutcomeToken(i) for i in pool_balances], fees
        )

        actual_price = bet_amount.value / tokens_to_buy.value
        # price_impact should always be > 0
        price_impact = (actual_price - expected_price) / expected_price
        return price_impact

    def calculate_bet_amount_for_price_impact(
        self, market: AgentMarket, kelly_bet: SimpleBet, direction: OutcomeStr
    ) -> CollateralToken:
        def calculate_price_impact_deviation_from_target_price_impact(
            bet_amount_usd: float,  # Needs to be float because it's used in minimize_scalar internally.
        ) -> float:
            outcome_idx = market.get_outcome_index(direction)
            price_impact = self.calculate_price_impact_for_bet_amount(
                outcome_idx=outcome_idx,
                bet_amount=market.get_usd_in_token(USD(bet_amount_usd)),
                pool_balances=pool_balances,
                fees=market.fees,
            )
            # We return abs for the algorithm to converge to 0 instead of the min (and possibly negative) value.

            max_price_impact = check_not_none(self.max_price_impact)
            return abs(price_impact - max_price_impact)

        if not market.outcome_token_pool:
            logger.warning(
                "Market outcome_token_pool is None, cannot calculate bet amount"
            )
            return kelly_bet.size

        pool_balances = [i.value for i in market.outcome_token_pool.values()]
        total_pool_balance = sum(pool_balances)

        # The bounds below have been found to work heuristically.
        optimized_bet_amount = minimize_scalar(
            calculate_price_impact_deviation_from_target_price_impact,
            bounds=(0, 1000 * total_pool_balance),
            method="bounded",
            tol=1e-11,
            options={"maxiter": 10000},
        )
        return CollateralToken(optimized_bet_amount.x)

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

        outcome = get_most_probable_outcome(answer.probabilities)

        if market.is_binary:
            # use Kelly full

            # Fixed direction of bet, only use Kelly to adjust the bet size based on market's outcome pool size.
            estimated_p_yes = (
                1.0 if outcome == market.get_outcome_str_from_bool(True) else 0.0
            )

            kelly_bet = get_kelly_bet_full(
                yes_outcome_pool_size=outcome_token_pool[
                    market.get_outcome_str_from_bool(True)
                ],
                no_outcome_pool_size=outcome_token_pool[
                    market.get_outcome_str_from_bool(False)
                ],
                estimated_p_yes=estimated_p_yes,
                max_bet=adjusted_bet_amount_token,
                confidence=1.0,
                fees=market.fees,
            )

        else:
            # use Kelly simple, since Kelly full only supports 2 outcomes
            kelly_bet = get_kelly_bet_simplified(
                max_bet=adjusted_bet_amount_token,
                market_p_yes=market.probabilities[outcome],
                estimated_p_yes=answer.probabilities[outcome],
                confidence=answer.confidence,
            )

        kelly_bet_size_usd = market.get_token_in_usd(kelly_bet.size)

        amounts = {
            outcome: kelly_bet_size_usd,
        }
        target_position = Position(market_id=market.id, amounts_current=amounts)

        trades = self._build_rebalance_trades_from_positions(
            existing_position=existing_position,
            target_position=target_position,
            market=market,
        )
        return trades

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}(max_bet_amount={self.max_bet_amount})"
