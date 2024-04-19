from prediction_market_agent_tooling.markets.agent_market import AgentMarket


def minimum_bet_to_win(
    answer: bool, amount_to_win: float, market: AgentMarket
) -> float:
    """
    Estimates the minimum bet amount to win the given amount based on the current market price.
    """
    share_price = market.current_p_yes if answer else market.current_p_no
    bet_amount = amount_to_win / (1 / share_price - 1)
    return bet_amount
