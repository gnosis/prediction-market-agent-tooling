import typing as t

from prediction_market_agent_tooling.gtypes import Decimal, Probability

BetCurrency = t.TypeVar("BetCurrency", bound=Decimal)


def stretch_bet_between(
    probability: Probability, min_bet: BetCurrency, max_bet: BetCurrency
) -> BetCurrency:
    """
    Normalise the outcome probability into a bet amount between the minimum and maximum bet.
    """
    return min_bet + (max_bet - min_bet) * probability
