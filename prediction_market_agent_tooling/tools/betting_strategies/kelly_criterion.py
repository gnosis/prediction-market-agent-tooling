from prediction_market_agent_tooling.tools.betting_strategies.utils import SimpleBet


def check_is_valid_probability(probability: float) -> None:
    if not 0 <= probability <= 1:
        raise ValueError("Probability must be between 0 and 1")


def get_kelly_bet_simplified(
    max_bet: float,
    market_p_yes: float,
    estimated_p_yes: float,
    confidence: float,
) -> SimpleBet:
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
    else:
        bet_direction = False
        market_prob = 1 - market_p_yes

    # Handle the case where market_prob is 0
    if market_prob == 0:
        market_prob = 1e-10

    edge = abs(estimated_p_yes - market_p_yes) * confidence
    odds = (1 / market_prob) - 1
    kelly_fraction = edge / odds

    # Ensure bet size is non-negative does not exceed the wallet balance
    bet_size = min(kelly_fraction * max_bet, max_bet)

    return SimpleBet(direction=bet_direction, size=bet_size)


def get_kelly_bet_full(
    yes_outcome_pool_size: float,
    no_outcome_pool_size: float,
    estimated_p_yes: float,
    confidence: float,
    max_bet: float,
    fee: float = 0.0,  # proportion, 0 to 1
) -> SimpleBet:
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
    check_is_valid_probability(estimated_p_yes)
    check_is_valid_probability(confidence)
    check_is_valid_probability(fee)

    if max_bet == 0:
        return SimpleBet(direction=True, size=0)

    x = yes_outcome_pool_size
    y = no_outcome_pool_size
    p = estimated_p_yes
    c = confidence
    b = max_bet
    f = 1 - fee

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
    if denominator == 0:
        breakpoint()
        return SimpleBet(direction=True, size=0)
    kelly_bet_amount = numerator / denominator

    return SimpleBet(direction=kelly_bet_amount > 0, size=abs(kelly_bet_amount))
