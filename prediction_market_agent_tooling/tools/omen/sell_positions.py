from datetime import timedelta

from prediction_market_agent_tooling.config import APIKeys
from prediction_market_agent_tooling.gtypes import USD
from prediction_market_agent_tooling.loggers import logger
from prediction_market_agent_tooling.markets.omen.omen import OmenAgentMarket
from prediction_market_agent_tooling.markets.omen.omen_subgraph_handler import (
    OmenSubgraphHandler,
)
from prediction_market_agent_tooling.tools.balances import get_balances
from prediction_market_agent_tooling.tools.utils import utcnow


def sell_all(
    api_keys: APIKeys,
    closing_later_than_days: int,
    auto_withdraw: bool = True,
) -> None:
    """
    Helper function to sell all existing outcomes on Omen that would resolve later than in X days.
    """
    better_address = api_keys.bet_from_address
    bets = OmenSubgraphHandler().get_bets(
        better_address=better_address,
        market_opening_after=utcnow() + timedelta(days=closing_later_than_days),
    )
    bets_total_usd = sum(
        (b.get_collateral_amount_usd() for b in bets), start=USD.zero()
    )
    unique_market_urls = set(b.fpmm.url for b in bets)
    starting_balance = get_balances(better_address)
    new_balance = starting_balance

    logger.info(
        f"For {better_address}, found the following {len(bets)} bets on {len(unique_market_urls)} unique markets worth of {bets_total_usd} USD: {unique_market_urls}"
    )

    for bet in bets:
        agent_market = OmenAgentMarket.from_data_model(bet.fpmm)
        outcome = agent_market.outcomes[bet.outcomeIndex]
        current_token_balance = agent_market.get_token_balance(better_address, outcome)

        if current_token_balance.as_token <= agent_market.get_tiny_bet_amount():
            logger.info(
                f"Skipping bet on {bet.fpmm.url} because the actual balance is unreasonably low {current_token_balance}."
            )
            continue

        old_balance = new_balance
        agent_market.sell_tokens(
            bet.boolean_outcome,
            current_token_balance,
            auto_withdraw=auto_withdraw,
            api_keys=api_keys,
        )
        new_balance = get_balances(better_address)

        logger.info(
            f"Sold bet on {bet.fpmm.url} for {new_balance.wxdai - old_balance.wxdai} xDai."
        )

    logger.info(f"Obtained back {new_balance.wxdai - starting_balance.wxdai} wxDai.")
