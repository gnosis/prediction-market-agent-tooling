from abc import ABC, abstractmethod
from typing import Sequence

import numpy as np
from scipy.optimize import minimize_scalar

from prediction_market_agent_tooling.benchmark.utils import get_most_probable_outcome
from prediction_market_agent_tooling.deploy.constants import (
    INVALID_OUTCOME_LOWERCASE_IDENTIFIER,
)
from prediction_market_agent_tooling.gtypes import (
    USD,
    CollateralToken,
    OutcomeStr,
    OutcomeWei,
    Probability,
)
from prediction_market_agent_tooling.loggers import logger
from prediction_market_agent_tooling.markets.agent_market import AgentMarket, MarketFees
from prediction_market_agent_tooling.markets.data_models import (
    CategoricalProbabilisticAnswer,
    ExistingPosition,
    Position,
    Trade,
    TradeType,
)
from prediction_market_agent_tooling.markets.omen.omen import (
    get_buy_outcome_token_amount,
)
from prediction_market_agent_tooling.tools.betting_strategies.kelly_criterion import (
    get_kelly_bet_full,
    get_kelly_bet_simplified,
    get_kelly_bets_categorical_full,
    get_kelly_bets_categorical_simplified,
)
from prediction_market_agent_tooling.tools.betting_strategies.utils import (
    BinaryKellyBet,
    CategoricalKellyBet,
)
from prediction_market_agent_tooling.tools.utils import check_not_none


class GuaranteedLossError(RuntimeError):
    pass


class BettingStrategy(ABC):
    def __init__(self, take_profit: bool = True) -> None:
        self.take_profit = take_profit

    @abstractmethod
    def calculate_trades(
        self,
        existing_position: ExistingPosition | None,
        answer: CategoricalProbabilisticAnswer,
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
                        f"Trade {trade=} on market {market.url=} would result in guaranteed loss by getting only {outcome_tokens_to_get=}. Halting execution."
                    )

            clean_trades.append(trade)

        return clean_trades

    @staticmethod
    def filter_trades(market: AgentMarket, trades: list[Trade]) -> list[Trade]:
        trades = BettingStrategy.assert_buy_trade_wont_be_guaranteed_loss(
            market, trades
        )
        return trades

    @staticmethod
    def cap_to_profitable_bet_amount(
        market: AgentMarket,
        bet_amount: USD,
        outcome: OutcomeStr,
        iters: int = 10,
    ) -> USD:
        """
        Use a binary search (tree-based search) to efficiently find the largest profitable bet amount.
        """
        # First, try it with the desired amount right away.
        if (
            market.get_in_usd(
                check_not_none(
                    market.get_buy_token_amount(bet_amount, outcome)
                ).as_token
            )
            > bet_amount
        ):
            return bet_amount

        # If it wasn't profitable, try binary search to find the highest, but profitable, amount.
        lower = USD(0)
        # It doesn't make sense to try to bet more than the liquidity itself, so override it as maximal value if it's lower.
        upper = min(bet_amount, market.get_in_usd(market.get_liquidity()))
        best_profitable = USD(0)

        for _ in range(iters):
            mid = (lower + upper) / 2
            potential_outcome_value = market.get_in_usd(
                check_not_none(market.get_buy_token_amount(mid, outcome)).as_token
            )

            if potential_outcome_value > mid:
                # Profitable, try higher
                best_profitable = mid
                lower = mid

            else:
                # Not profitable, try lower
                upper = mid

            # If the search interval is very small, break early
            if float(upper - lower) < 1e-8:
                break

        if np.isclose(best_profitable.value, 0):
            best_profitable = USD(0)

        return best_profitable

    @staticmethod
    def cap_to_profitable_position(
        market: AgentMarket,
        existing_position: USD,
        wanted_position: USD,
        outcome_to_bet_on: OutcomeStr,
    ) -> USD:
        # If the wanted position is lower, it means the agent is gonna sell and that's profitable always.
        if wanted_position > existing_position:
            difference = wanted_position - existing_position
            # Cap the difference we would like to buy to a profitable one.
            capped_difference = BettingStrategy.cap_to_profitable_bet_amount(
                market, difference, outcome_to_bet_on
            )
            # Lowered the actual wanted position such that it remains profitable.
            wanted_position = existing_position + capped_difference

        return wanted_position

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
        Note that we order the trades to first buy then sell, in order to minimally tilt the odds so that sell price is higher.
        """

        existing_amounts = (
            {
                outcome.lower(): amount
                for outcome, amount in existing_position.amounts_current.items()
            }
            if existing_position
            else {}
        )
        target_amounts = (
            {
                outcome.lower(): amount
                for outcome, amount in target_position.amounts_current.items()
            }
            if target_position
            else {}
        )

        trades = []
        for outcome in market.outcomes:
            existing_amount = existing_amounts.get(
                outcome.lower(), self.build_zero_usd_amount()
            )
            target_amount = target_amounts.get(
                outcome.lower(), self.build_zero_usd_amount()
            )

            diff_amount = target_amount - existing_amount

            if diff_amount == 0:
                continue

            trade_type = TradeType.SELL if diff_amount < 0 else TradeType.BUY

            # We work with positions, so imagine following scenario: Agent invested $10 when probs were 50:50,
            # now the probs are 99:1 and his initial $10 is worth $100.
            # If `take_profit` is set to False, agent won't sell the $90 to get back to the $10 position.
            if (
                not self.take_profit
                and target_amount > 0
                and trade_type == TradeType.SELL
            ):
                continue

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


class CategoricalMaxAccuracyBettingStrategy(BettingStrategy):
    def __init__(self, max_position_amount: USD, take_profit: bool = True):
        super().__init__(take_profit=take_profit)
        self.max_position_amount = max_position_amount

    @property
    def maximum_possible_bet_amount(self) -> USD:
        return self.max_position_amount

    @staticmethod
    def calculate_direction(
        market: AgentMarket, answer: CategoricalProbabilisticAnswer
    ) -> OutcomeStr:
        # We place a bet on the most likely outcome
        most_likely_outcome = max(
            answer.probabilities.items(),
            key=lambda item: item[1],
        )[0]

        return market.market_outcome_for_probability_key(most_likely_outcome)

    @staticmethod
    def get_other_direction(
        outcomes: Sequence[OutcomeStr], direction: OutcomeStr
    ) -> OutcomeStr:
        # We get the first direction which is != direction.
        other_direction = [i for i in outcomes if i.lower() != direction.lower()][0]
        if INVALID_OUTCOME_LOWERCASE_IDENTIFIER in other_direction.lower():
            raise ValueError("Invalid outcome found as opposite direction. Exitting.")
        return other_direction

    def calculate_trades(
        self,
        existing_position: ExistingPosition | None,
        answer: CategoricalProbabilisticAnswer,
        market: AgentMarket,
    ) -> list[Trade]:
        """We place bet on only one outcome."""
        outcome_to_bet_on = self.calculate_direction(market, answer)

        # Will be lowered if the amount that we would need to buy would be unprofitable.
        actual_wanted_position = BettingStrategy.cap_to_profitable_position(
            market,
            (
                existing_position.amounts_current.get(outcome_to_bet_on, USD(0))
                if existing_position
                else USD(0)
            ),
            self.max_position_amount,
            outcome_to_bet_on,
        )

        target_position = Position(
            market_id=market.id,
            amounts_current={outcome_to_bet_on: actual_wanted_position},
        )
        trades = self._build_rebalance_trades_from_positions(
            existing_position=existing_position,
            target_position=target_position,
            market=market,
        )
        return trades

    def __repr__(self) -> str:
        return f"CategoricalMaxAccuracyBettingStrategy(max_position_amount={self.max_position_amount}, take_profit={self.take_profit})"


class MaxExpectedValueBettingStrategy(CategoricalMaxAccuracyBettingStrategy):
    @staticmethod
    def calculate_direction(
        market: AgentMarket, answer: CategoricalProbabilisticAnswer
    ) -> OutcomeStr:
        """
        Returns the index of the outcome with the highest expected value.
        """

        missing_outcomes = set([i.lower() for i in market.outcomes]) - set(
            [i.lower() for i in market.probabilities.keys()]
        )

        if missing_outcomes:
            raise ValueError(
                f"Outcomes {missing_outcomes} not found in answer probabilities {answer.probabilities}"
            )

        best_outcome = None
        best_ev = float("-inf")
        for market_outcome in market.outcomes:
            if market.probability_for_market_outcome(market_outcome) == Probability(
                0.0
            ):
                # avoid division by 0
                continue

            ev = answer.probability_for_market_outcome(
                market_outcome
            ) / market.probability_for_market_outcome(market_outcome)
            if ev > best_ev:
                best_ev = ev
                best_outcome = market_outcome

        if best_outcome is None:
            raise ValueError(
                "Cannot determine best outcome - all market probabilities are zero"
            )

        return best_outcome

    def __repr__(self) -> str:
        return f"MaxExpectedValueBettingStrategy(max_position_amount={self.max_position_amount}, take_profit={self.take_profit})"


class BinaryKellyBettingStrategy(BettingStrategy):
    def __init__(
        self,
        max_position_amount: USD,
        max_price_impact: float | None = None,
        take_profit: bool = True,
        force_simplified_calculation: bool = False,
    ):
        super().__init__(take_profit=take_profit)
        self.max_position_amount = max_position_amount
        self.max_price_impact = max_price_impact
        self.force_simplified_calculation = force_simplified_calculation

    @property
    def maximum_possible_bet_amount(self) -> USD:
        return self.max_position_amount

    def get_kelly_bet(
        self,
        market: AgentMarket,
        direction: OutcomeStr,
        other_direction: OutcomeStr,
        answer: CategoricalProbabilisticAnswer,
        override_p_yes: float | None = None,
    ) -> BinaryKellyBet:
        estimated_p_yes = (
            answer.probability_for_market_outcome(direction)
            if not override_p_yes
            else override_p_yes
        )

        if market.outcome_token_pool is None or self.force_simplified_calculation:
            kelly_bet = get_kelly_bet_simplified(
                max_bet=market.get_usd_in_token(self.max_position_amount),
                market_p_yes=market.probability_for_market_outcome(direction),
                estimated_p_yes=estimated_p_yes,
                confidence=answer.confidence,
            )
        else:
            direction_to_bet_pool_size = market.get_outcome_token_pool_by_outcome(
                direction
            )
            other_direction_pool_size = market.get_outcome_token_pool_by_outcome(
                other_direction
            )
            kelly_bet = get_kelly_bet_full(
                yes_outcome_pool_size=direction_to_bet_pool_size,
                no_outcome_pool_size=other_direction_pool_size,
                estimated_p_yes=estimated_p_yes,
                max_bet=market.get_usd_in_token(self.max_position_amount),
                confidence=answer.confidence,
                fees=market.fees,
            )
        return kelly_bet

    def calculate_trades(
        self,
        existing_position: ExistingPosition | None,
        answer: CategoricalProbabilisticAnswer,
        market: AgentMarket,
    ) -> list[Trade]:
        # We consider the p_yes as the direction with highest probability.
        direction = CategoricalMaxAccuracyBettingStrategy.calculate_direction(
            market, answer
        )
        # We get the first direction which is != direction.
        other_direction = [i for i in market.outcomes if i != direction][0]
        if INVALID_OUTCOME_LOWERCASE_IDENTIFIER in other_direction.lower():
            raise ValueError("Invalid outcome found as opposite direction. Exitting.")

        kelly_bet = self.get_kelly_bet(
            market=market,
            direction=direction,
            other_direction=other_direction,
            answer=answer,
        )

        kelly_bet_size = kelly_bet.size
        if self.max_price_impact:
            # Adjust amount
            max_price_impact_bet_amount = self.calculate_bet_amount_for_price_impact(
                market,
                kelly_bet.size,
                direction=direction,
                max_price_impact=self.max_price_impact,
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

    @staticmethod
    def calculate_price_impact_for_bet_amount(
        outcome_idx: int,
        bet_amount: CollateralToken,
        pool_balances: list[OutcomeWei],
        fees: MarketFees,
    ) -> float:
        prices = AgentMarket.compute_fpmm_probabilities(pool_balances)
        expected_price = prices[outcome_idx]

        tokens_to_buy = get_buy_outcome_token_amount(
            bet_amount, outcome_idx, [i.as_outcome_token for i in pool_balances], fees
        )

        actual_price = bet_amount.value / tokens_to_buy.value
        # price_impact should always be > 0
        price_impact = (actual_price - expected_price) / expected_price
        return price_impact

    @staticmethod
    def calculate_bet_amount_for_price_impact(
        market: AgentMarket,
        kelly_bet_size: CollateralToken,
        direction: OutcomeStr,
        max_price_impact: float,
    ) -> CollateralToken:
        def calculate_price_impact_deviation_from_target_price_impact(
            bet_amount_collateral: float,  # Needs to be float because it's used in minimize_scalar internally.
        ) -> float:
            outcome_idx = market.get_outcome_index(direction)
            price_impact = (
                BinaryKellyBettingStrategy.calculate_price_impact_for_bet_amount(
                    outcome_idx=outcome_idx,
                    bet_amount=CollateralToken(bet_amount_collateral),
                    pool_balances=pool_balances,
                    fees=market.fees,
                )
            )
            # We return abs for the algorithm to converge to 0 instead of the min (and possibly negative) value.
            return abs(price_impact - max_price_impact)

        if not market.outcome_token_pool:
            logger.warning(
                "Market outcome_token_pool is None, cannot calculate bet amount"
            )
            return kelly_bet_size

        pool_balances = [i.as_outcome_wei for i in market.outcome_token_pool.values()]
        # stay float for compatibility with `minimize_scalar`
        total_pool_balance = sum([i.value for i in market.outcome_token_pool.values()])

        # The bounds below have been found to work heuristically.
        optimized_bet_amount = minimize_scalar(
            calculate_price_impact_deviation_from_target_price_impact,
            bounds=(0, 1000 * total_pool_balance),
            method="bounded",
            tol=1e-13,
            options={"maxiter": 10000},
        )
        return CollateralToken(optimized_bet_amount.x)

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}(max_position_amount={self.max_position_amount}, max_price_impact={self.max_price_impact}, take_profit={self.take_profit}, force_simplified_calculation={self.force_simplified_calculation})"


class MaxAccuracyWithKellyScaledBetsStrategy(BettingStrategy):
    def __init__(
        self,
        max_position_amount: USD,
        take_profit: bool = True,
    ):
        super().__init__(take_profit)
        self.max_position_amount = max_position_amount

    @property
    def maximum_possible_bet_amount(self) -> USD:
        return self.max_position_amount

    def calculate_trades(
        self,
        existing_position: ExistingPosition | None,
        answer: CategoricalProbabilisticAnswer,
        market: AgentMarket,
    ) -> list[Trade]:
        outcome = get_most_probable_outcome(answer.probabilities)

        direction = CategoricalMaxAccuracyBettingStrategy.calculate_direction(
            market, answer
        )
        # We get the first direction which is != direction.
        other_direction = CategoricalMaxAccuracyBettingStrategy.get_other_direction(
            outcomes=market.outcomes, direction=direction
        )

        # We ignore the direction nudge given by Kelly, hence we assume we have a perfect prediction.
        estimated_p_yes = 1.0

        kelly_bet = BinaryKellyBettingStrategy(
            max_position_amount=self.max_position_amount
        ).get_kelly_bet(
            market=market,
            direction=direction,
            other_direction=other_direction,
            answer=answer,
            override_p_yes=estimated_p_yes,
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
        return f"{self.__class__.__name__}(max_position_amount={self.max_position_amount}, take_profit={self.take_profit})"


class CategoricalKellyBettingStrategy(BettingStrategy):
    def __init__(
        self,
        max_position_amount: USD,
        max_price_impact: float | None,
        allow_multiple_bets: bool,
        allow_shorting: bool,
        multicategorical: bool,
        take_profit: bool = True,
        force_simplified_calculation: bool = False,
    ):
        super().__init__(take_profit=take_profit)
        self.max_position_amount = max_position_amount
        self.max_price_impact = max_price_impact
        self.allow_multiple_bets = allow_multiple_bets
        self.allow_shorting = allow_shorting
        self.multicategorical = multicategorical
        self.force_simplified_calculation = force_simplified_calculation

    @property
    def maximum_possible_bet_amount(self) -> USD:
        return self.max_position_amount

    def get_kelly_bets(
        self,
        market: AgentMarket,
        max_bet_amount: USD,
        answer: CategoricalProbabilisticAnswer,
    ) -> list[CategoricalKellyBet]:
        max_bet = market.get_usd_in_token(max_bet_amount)

        if market.outcome_token_pool is None or self.force_simplified_calculation:
            kelly_bets = get_kelly_bets_categorical_simplified(
                market_probabilities=[market.probabilities[o] for o in market.outcomes],
                estimated_probabilities=[
                    answer.probability_for_market_outcome(o) for o in market.outcomes
                ],
                confidence=answer.confidence,
                max_bet=max_bet,
                fees=market.fees,
                allow_multiple_bets=self.allow_multiple_bets,
                allow_shorting=self.allow_shorting,
            )

        else:
            kelly_bets = get_kelly_bets_categorical_full(
                outcome_pool_sizes=[
                    market.outcome_token_pool[o] for o in market.outcomes
                ],
                estimated_probabilities=[
                    answer.probability_for_market_outcome(o) for o in market.outcomes
                ],
                confidence=answer.confidence,
                max_bet=max_bet,
                fees=market.fees,
                allow_multiple_bets=self.allow_multiple_bets,
                allow_shorting=self.allow_shorting,
                multicategorical=self.multicategorical,
            )

        return kelly_bets

    def calculate_trades(
        self,
        existing_position: ExistingPosition | None,
        answer: CategoricalProbabilisticAnswer,
        market: AgentMarket,
    ) -> list[Trade]:
        kelly_bets = self.get_kelly_bets(
            market=market,
            max_bet_amount=self.max_position_amount,
            answer=answer,
        )

        # TODO: Allow shorting in BettingStrategy._build_rebalance_trades_from_positions.
        # In binary implementation, we simply flip the direction in case of negative bet, for categorical outcome, we need to implement shorting.
        kelly_bets = [bet for bet in kelly_bets if bet.size > 0]
        if not kelly_bets:
            return []

        # TODO: Allow betting on multiple outcomes.
        # Categorical kelly could suggest to bet on multiple outcomes, but we only consider the first one for now (limitation of BettingStrategy `trades` creation).
        # Also, this could maybe work for multi-categorical markets as well, but it wasn't benchmarked for it.
        best_kelly_bet = max(kelly_bets, key=lambda x: abs(x.size))

        if self.max_price_impact:
            # Adjust amount
            max_price_impact_bet_amount = (
                BinaryKellyBettingStrategy.calculate_bet_amount_for_price_impact(
                    market,
                    best_kelly_bet.size,
                    direction=market.get_outcome_str(best_kelly_bet.index),
                    max_price_impact=self.max_price_impact,
                )
            )
            # We just don't want Kelly size to extrapolate price_impact - hence we take the min.
            best_kelly_bet.size = min(best_kelly_bet.size, max_price_impact_bet_amount)

        amounts = {
            market.outcomes[best_kelly_bet.index]: market.get_token_in_usd(
                best_kelly_bet.size
            ),
        }
        target_position = Position(market_id=market.id, amounts_current=amounts)
        trades = self._build_rebalance_trades_from_positions(
            existing_position, target_position, market=market
        )

        return trades

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}(max_position_amount={self.max_position_amount}, max_price_impact={self.max_price_impact}, allow_multiple_bets={self.allow_multiple_bets}, allow_shorting={self.allow_shorting}, take_profit={self.take_profit}, force_simplified_calculation={self.force_simplified_calculation})"
