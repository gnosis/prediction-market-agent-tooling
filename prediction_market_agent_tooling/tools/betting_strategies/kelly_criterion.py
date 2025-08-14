from itertools import chain

import numpy as np
from scipy.optimize import minimize

from prediction_market_agent_tooling.gtypes import (
    CollateralToken,
    OutcomeToken,
    Probability,
)
from prediction_market_agent_tooling.loggers import logger
from prediction_market_agent_tooling.markets.agent_market import AgentMarket
from prediction_market_agent_tooling.markets.market_fees import MarketFees
from prediction_market_agent_tooling.markets.omen.omen import (
    calculate_buy_outcome_token,
)
from prediction_market_agent_tooling.tools.betting_strategies.utils import (
    BinaryKellyBet,
    CategoricalKellyBet,
)
from prediction_market_agent_tooling.tools.utils import check_not_none


def check_is_valid_probability(probability: float) -> None:
    if not 0 <= probability <= 1:
        raise ValueError("Probability must be between 0 and 1")


def get_kelly_bet_simplified(
    max_bet: CollateralToken,
    market_p_yes: float,
    estimated_p_yes: float,
    confidence: float,
) -> BinaryKellyBet:
    """
    Calculate the optimal bet amount using the Kelly Criterion for a binary outcome market.

    From https://en.wikipedia.org/wiki/Kelly_criterion:

    f* = p - q / b

    where:
    - f* is the fraction of the current bankroll to wager
    - p is the probability of a win
    - q = 1-p is the probability of a loss
    - b is the proportion of the bet gained with a win

    Note: this calculation does not factor in that the bet changes the market
    odds. This means the calculation is only accurate if the bet size is small
    compared to the market volume. See discussion here for more detail:
    https://github.com/gnosis/prediction-market-agent-tooling/pull/330#discussion_r1698269328
    """
    check_is_valid_probability(market_p_yes)
    check_is_valid_probability(estimated_p_yes)
    check_is_valid_probability(confidence)

    if estimated_p_yes > market_p_yes:
        bet_direction = True
        market_prob = market_p_yes
        estimated_p = estimated_p_yes
    else:
        bet_direction = False
        market_prob = 1 - market_p_yes
        estimated_p = 1 - estimated_p_yes

    # Handle the case where market_prob is 0
    if market_prob == 0:
        market_prob = 1e-10

    edge = abs(estimated_p - market_prob) * confidence
    odds = (1 / market_prob) - 1
    kelly_fraction = edge / odds

    # Ensure bet size is non-negative does not exceed the wallet balance
    bet_size = CollateralToken(min(kelly_fraction * max_bet.value, max_bet.value))

    return BinaryKellyBet(direction=bet_direction, size=bet_size)


def get_kelly_bet_full(
    yes_outcome_pool_size: OutcomeToken,
    no_outcome_pool_size: OutcomeToken,
    estimated_p_yes: float,
    confidence: float,
    max_bet: CollateralToken,
    fees: MarketFees,
) -> BinaryKellyBet:
    """
    Calculate the optimal bet amount using the Kelly Criterion for a binary outcome market.

    'Full' as in it accounts for how the bet changes the market odds.

    Taken from https://github.com/valory-xyz/trader/blob/main/strategies/kelly_criterion/kelly_criterion.py

    with derivation in PR description: https://github.com/valory-xyz/trader/pull/119

    ```
    Licensed under the Apache License, Version 2.0 (the "License");
    you may not use this file except in compliance with the License.
    You may obtain a copy of the License at

        http://www.apache.org/licenses/LICENSE-2.0

    Unless required by applicable law or agreed to in writing, software
    distributed under the License is distributed on an "AS IS" BASIS,
    WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
    See the License for the specific language governing permissions and
    limitations under the License.
    ```
    """
    fee = fees.bet_proportion
    if fees.absolute > 0:
        raise RuntimeError(
            f"Kelly works only with bet-proportional fees, but the fees are {fees=}."
        )

    check_is_valid_probability(estimated_p_yes)
    check_is_valid_probability(confidence)

    if max_bet == 0:
        return BinaryKellyBet(size=CollateralToken(0), direction=True)

    x = yes_outcome_pool_size.value
    y = no_outcome_pool_size.value
    p = estimated_p_yes
    c = confidence
    b = max_bet.value
    f = 1 - fee

    if x == y:
        # Add a delta to prevent division by zero
        y += 1e-10

    numerator = (
        -4 * x**2 * y
        + b * y**2 * p * c * f
        + 2 * b * x * y * p * c * f
        + b * x**2 * p * c * f
        - 2 * b * y**2 * f
        - 2 * b * x * y * f
        + (
            (
                4 * x**2 * y
                - b * y**2 * p * c * f
                - 2 * b * x * y * p * c * f
                - b * x**2 * p * c * f
                + 2 * b * y**2 * f
                + 2 * b * x * y * f
            )
            ** 2
            - (
                4
                * (x**2 * f - y**2 * f)
                * (
                    -4 * b * x * y**2 * p * c
                    - 4 * b * x**2 * y * p * c
                    + 4 * b * x * y**2
                )
            )
        )
        ** (1 / 2)
    )
    denominator = 2 * (x**2 * f - y**2 * f)
    kelly_bet_amount = numerator / denominator

    # Clip the bet size to max_bet to account for rounding errors.
    return BinaryKellyBet(
        direction=kelly_bet_amount > 0,
        size=CollateralToken(min(max_bet.value, abs(kelly_bet_amount))),
    )


def get_kelly_bets_categorical_simplified(
    market_probabilities: list[Probability],
    estimated_probabilities: list[Probability],
    confidence: float,
    max_bet: CollateralToken,
    fees: MarketFees,
    allow_multiple_bets: bool,
    allow_shorting: bool,
    bet_precision: int = 6,
) -> list[CategoricalKellyBet]:
    """
    Calculate Kelly bets for categorical markets using only market probabilities.
    Returns a list of CategoricalKellyBet objects, one for each outcome.
    Considers max_bet across all outcomes together.
    Indicates both buying (long) and shorting (selling) by allowing negative bet sizes.
    """
    for p in chain(market_probabilities, estimated_probabilities, [confidence]):
        check_is_valid_probability(p)
    assert len(market_probabilities) == len(
        estimated_probabilities
    ), "Mismatch in number of outcomes"

    f = 1 - fees.bet_proportion

    total_kelly_fraction = 0.0
    kelly_fractions = []

    for i in range(len(market_probabilities)):
        estimated_p = estimated_probabilities[i]
        market_p = max(market_probabilities[i], 1e-10)

        edge = (estimated_p - market_p) * confidence
        odds = (1 / market_p) - 1
        kelly_fraction = edge / odds * f

        if not allow_shorting:
            kelly_fraction = max(0, kelly_fraction)

        kelly_fractions.append(kelly_fraction)
        total_kelly_fraction += abs(kelly_fraction)

    best_kelly_fraction_index = max(
        range(len(kelly_fractions)), key=lambda i: abs(kelly_fractions[i])
    )

    bets = []
    for i, kelly_fraction in enumerate(kelly_fractions):
        if not allow_multiple_bets:
            bet_size = (
                kelly_fraction * max_bet.value if i == best_kelly_fraction_index else 0
            )
        elif allow_multiple_bets and total_kelly_fraction > 0:
            bet_size = (kelly_fraction / total_kelly_fraction) * max_bet.value
        else:
            bet_size = 0.0
        # Ensure bet_size is within [-max_bet.value, max_bet.value]
        bet_size = max(-max_bet.value, min(bet_size, max_bet.value))
        bets.append(
            CategoricalKellyBet(
                index=i, size=CollateralToken(round(bet_size, bet_precision))
            )
        )

    return bets


def get_kelly_bets_categorical_full(
    outcome_pool_sizes: list[OutcomeToken],
    estimated_probabilities: list[Probability],
    confidence: float,
    max_bet: CollateralToken,
    fees: MarketFees,
    allow_multiple_bets: bool,
    allow_shorting: bool,
    multicategorical: bool,
    bet_precision: int = 6,
) -> list[CategoricalKellyBet]:
    """
    Calculate Kelly bets for categorical markets using joint optimization over all outcomes,
    splitting the max bet between all possible outcomes to maximize expected log utility.
    Returns a list of CategoricalKellyBet objects, one for each outcome.
    Handles both buying (long) and shorting (selling) by allowing negative bet sizes.
    If the agent's probabilities are very close to the market's, returns all-zero bets.
    multicategorical means that multiple outcomes could be selected as correct ones.
    """
    assert len(outcome_pool_sizes) == len(
        estimated_probabilities
    ), "Mismatch in number of outcomes"

    market_probabilities = AgentMarket.compute_fpmm_probabilities(
        [x.as_outcome_wei for x in outcome_pool_sizes]
    )

    for p in chain(market_probabilities, estimated_probabilities, [confidence]):
        check_is_valid_probability(p)

    n = len(outcome_pool_sizes)
    max_bet_value = max_bet.value

    if all(
        abs(estimated_probabilities[i] - market_probabilities[i]) < 1e-3
        for i in range(n)
    ):
        return [
            CategoricalKellyBet(index=i, size=CollateralToken(0.0)) for i in range(n)
        ]

    def compute_payouts(bets: list[float]) -> list[float]:
        payouts: list[float] = []
        for i in range(n):
            payout = 0.0
            if bets[i] >= 0:
                # If bet on i is positive, we buy outcome i
                buy_result = calculate_buy_outcome_token(
                    CollateralToken(bets[i]), i, outcome_pool_sizes, fees
                )
                payout += buy_result.outcome_tokens_received.value
            else:
                # If bet is negative, we "short" outcome i by buying all other outcomes
                for j in range(n):
                    if j == i:
                        continue
                    buy_result = calculate_buy_outcome_token(
                        CollateralToken(abs(bets[i]) / (n - 1)),
                        j,
                        outcome_pool_sizes,
                        fees,
                    )
                    payout += buy_result.outcome_tokens_received.value
            payouts.append(payout)
        return payouts

    def adjust_prob(my_prob: float, market_prob: float) -> float:
        # Based on the confidence, shrinks the predicted probability towards market's current probability.
        return confidence * my_prob + (1 - confidence) * market_prob

    # Use the simple version to estimate the initial bet vector.
    x0 = np.array(
        [
            x.size.value  # Use simplified value as starting point
            for x in get_kelly_bets_categorical_simplified(
                market_probabilities=market_probabilities,
                estimated_probabilities=estimated_probabilities,
                confidence=confidence,
                max_bet=max_bet,
                fees=fees,
                allow_multiple_bets=allow_multiple_bets,
                allow_shorting=allow_shorting,
                bet_precision=bet_precision,
            )
        ]
    )

    # Track the best solution found during optimization
    best_solution_bets = None
    best_solution_utility = float("-inf")

    def neg_expected_log_utility(bets: list[float]) -> float:
        """
        Negative expected log utility for categorical Kelly betting.
        This function is minimized to find the optimal bet allocation.
        """
        adj_probs = [
            adjust_prob(estimated_probabilities[i], market_probabilities[i])
            for i in range(n)
        ]
        payouts = compute_payouts(bets)

        profits = [payout - abs(bet) for payout, bet in zip(payouts, bets)]

        # Ensure profits are not too negative to avoid log(negative) or log(0)
        # Use a small epsilon to prevent numerical instability
        min_profit = -0.99  # Ensure 1 + profit > 0.01
        profits = [max(profit, min_profit) for profit in profits]

        # Expected log utility
        expected_log_utility: float = sum(
            adj_probs[i] * np.log(1 + profits[i]) for i in range(n)
        )

        # Track the best solution found so far
        nonlocal best_solution_bets, best_solution_utility
        if expected_log_utility > best_solution_utility:
            best_solution_bets = np.array(bets)
            best_solution_utility = expected_log_utility

        # Return negative for minimization
        return -expected_log_utility

    constraints = [
        # We can not bet more than `max_bet_value`
        {
            "type": "ineq",
            "fun": lambda bets: max_bet_value - np.sum(np.abs(bets)),
        },
        # Each bet should not result in guaranteed loss
        {
            "type": "ineq",
            "fun": lambda bets: [
                payout
                - (sum(abs(b) for b in bets) if not multicategorical else abs(bets[i]))
                for i, payout in enumerate(compute_payouts(bets))
            ],
        },
    ]

    result = minimize(
        neg_expected_log_utility,
        x0,
        method="SLSQP",
        bounds=[
            ((-max_bet_value if allow_shorting else 0), max_bet_value) for _ in range(n)
        ],
        constraints=constraints,
        options={"maxiter": 10_000},
    )

    # This can sometimes happen, as long as it's occasional, it's should be fine to just use simplified version approximation.
    if not result.success:
        logger.warning(
            f"Joint optimization failed: {result=} {x0=} {estimated_probabilities=} {confidence=} {market_probabilities=}"
        )

    # Use the best solution found during optimization, not just the final result (result.x).
    # This is important because SLSQP may end on a worse solution due to numerical issues.
    bet_vector = check_not_none(best_solution_bets) if result.success else x0

    if not allow_multiple_bets:
        # If we are not allowing multiple bets, we need to ensure only one bet is non-zero.
        # We can do this by taking the maximum bet and setting all others to zero.
        # We do this, instead of enforcing it in with additional constraint,
        # because such hard constraint is problematic for the solver and results in almost always failing to optimize.
        max_bet_index = np.argmax(np.abs(bet_vector))
        max_bet_value = bet_vector[max_bet_index]

        bet_vector = np.zeros_like(bet_vector)
        bet_vector[max_bet_index] = max_bet_value

    bets = [
        CategoricalKellyBet(
            index=i, size=CollateralToken(round(bet_vector[i], bet_precision))
        )
        for i in range(n)
    ]

    return bets
