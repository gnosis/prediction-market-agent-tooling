from math import ceil

from prediction_market_agent_tooling.markets.agent_market import AgentMarket
from prediction_market_agent_tooling.markets.data_models import Currency


def minimum_bet_to_win(
    answer: bool, amount_to_win: float, market: AgentMarket
) -> float:
    """
    Estimates the minimum bet amount to win the given amount based on the current market price.
    """
    share_price = market.p_yes if answer else market.p_no
    bet_amount = amount_to_win / (1 / share_price - 1)
    return bet_amount


def minimum_bet_to_win_manifold(
    answer: bool, amount_to_win: float, market: AgentMarket
) -> int:
    if market.currency != Currency.Mana:
        raise ValueError(f"Manifold bets are made in Mana. Got {market.currency}.")
    # Manifold lowest bet is 1 Mana, so we need to ceil the result.
    return ceil(minimum_bet_to_win(answer, amount_to_win, market))
