from enum import Enum


class BetOutcome(str, Enum):
    YES = "Yes"
    NO = "No"


def check_is_valid_probability(probability: float) -> None:
    if not 0 <= probability <= 1:
        raise ValueError("Probability must be between 0 and 1")


def get_kelly_bet(
    max_bet: float,
    market_p_yes: float,
    estimated_p_yes: float,
    confidence: float,
    bet_outcome: BetOutcome,
) -> float:
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
