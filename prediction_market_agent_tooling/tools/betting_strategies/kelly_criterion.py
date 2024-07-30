import typing as t

from prediction_market_agent_tooling.gtypes import Probability, wei_type, xDai
from prediction_market_agent_tooling.markets.omen.data_models import OmenMarket
from prediction_market_agent_tooling.tools.utils import check_not_none
from prediction_market_agent_tooling.tools.web3_utils import (
    ONE_XDAI,
    wei_to_xdai,
    xdai_to_wei,
)

OutcomeIndex = t.Literal[0, 1]

from enum import Enum


class BetOutcome(str, Enum):
    YES = "yes"
    NO = "no"


def check_is_valid_probability(probability: float) -> bool:
    if probability < 0 or probability > 1:
        raise ValueError("Probability must be between 0 and 1")


def get_kelly_bet_simplified(
    max_bet: float,
    market_p_yes: float,
    estimated_p_yes: float,
    confidence: float,
    bet_outcome: BetOutcome,
) -> float:
    """
    Calculate the optimal bet amount using the Kelly Criterion for a binary outcome market.

    Based on https://en.wikipedia.org/wiki/Kelly_criterion

    'Simplified' in that it is assumes that the bet does not change the market odds.
    """
    check_is_valid_probability(market_p_yes)
    check_is_valid_probability(estimated_p_yes)
    check_is_valid_probability(confidence)

    if bet_outcome == BetOutcome.YES:
        my_prob = estimated_p_yes
        market_prob = market_p_yes
    elif bet_outcome == BetOutcome.NO:
        my_prob = 1 - estimated_p_yes
        market_prob = 1 - market_p_yes

    edge = (my_prob - market_prob) * confidence

    # Handle the case where market_prob is 0
    if market_prob == 0:
        market_prob = 1e-10

    odds = (1 / market_prob) - 1
    kelly_fraction = edge / odds

    # Ensure bet size is non-negative does not exceed the wallet balance
    bet_size = max(min(kelly_fraction * max_bet, max_bet), 0)

    return bet_size


def _get_kelly_criterion_bet(
    x: int, y: int, p: float, c: float, b: int, f: float
) -> int:
    """
    Implments https://en.wikipedia.org/wiki/Kelly_criterion

    Taken from https://github.com/valory-xyz/trader/blob/main/strategies/kelly_criterion/kelly_criterion.py

    Takes into account how the bet changes the market odds.
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

    x: Number of tokens in the selected outcome pool
    y: Number of tokens in the other outcome pool
    p: Probability of winning
    c: Confidence
    b: Bankroll
    f: Fee fraction
    """
    if b == 0:
        return 0
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
        return 0
    kelly_bet_amount = numerator / denominator
    return int(kelly_bet_amount)


def get_kelly_criterion_bet(
    market: OmenMarket,
    estimated_p_yes: Probability,
    max_bet: xDai,
) -> t.Tuple[xDai, OutcomeIndex]:
    if len(market.outcomeTokenAmounts) != 2:
        raise ValueError("Only binary markets are supported.")

    current_p_yes = check_not_none(
        market.outcomeTokenProbabilities, "No probabilities, is marked closed?"
    )[0]
    outcome_index: OutcomeIndex = 0 if estimated_p_yes > current_p_yes else 1
    estimated_p_win = estimated_p_yes if outcome_index == 0 else 1 - estimated_p_yes

    kelly_bet_wei = wei_type(
        _get_kelly_criterion_bet(
            x=market.outcomeTokenAmounts[outcome_index],
            y=market.outcomeTokenAmounts[1 - outcome_index],
            p=estimated_p_win,
            c=1,  # confidence
            b=xdai_to_wei(max_bet),  # bankroll, or max bet, in Wei
            f=(
                xdai_to_wei(ONE_XDAI)
                - check_not_none(market.fee, "No fee for the market.")
            )
            / xdai_to_wei(ONE_XDAI),  # fee fraction
        )
    )
    return wei_to_xdai(kelly_bet_wei), outcome_index


def get_kelly_criterion_bet_2(
    market: OmenMarket,
    estimated_p_yes: Probability,
    max_bet: xDai,
) -> t.Tuple[xDai, OutcomeIndex]:
    if len(market.outcomeTokenAmounts) != 2:
        raise ValueError("Only binary markets are supported.")

    current_p_yes = check_not_none(
        market.outcomeTokenProbabilities, "No probabilities, is marked closed?"
    )[0]
    outcome_index: OutcomeIndex = 0 if estimated_p_yes > current_p_yes else 1
    bet_outcome = BetOutcome.YES if outcome_index == 0 else BetOutcome.NO
    bet = kelly_bet(
        wallet_balance=max_bet,
        market_p_yes=current_p_yes,
        my_p_yes=estimated_p_yes,
        confidence=1,
        bet_outcome=bet_outcome,
    )
    return bet, outcome_index
