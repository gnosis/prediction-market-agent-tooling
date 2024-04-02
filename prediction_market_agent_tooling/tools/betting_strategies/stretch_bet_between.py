from prediction_market_agent_tooling.gtypes import Probability


def stretch_bet_between(
    probability: Probability, min_bet: float, max_bet: float
) -> float:
    """
    Normalise the outcome probability into a bet amount between the minimum and maximum bet.
    """
    if min_bet > max_bet:
        raise ValueError("Minimum bet cannot be greater than maximum bet.")
    return min_bet + (max_bet - min_bet) * probability
