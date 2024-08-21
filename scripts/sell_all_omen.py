from datetime import timedelta

import typer
from web3 import Web3

from prediction_market_agent_tooling.config import APIKeys
from prediction_market_agent_tooling.deploy.betting_strategy import MINIMUM_BET_OMEN
from prediction_market_agent_tooling.gtypes import private_key_type
from prediction_market_agent_tooling.loggers import logger
from prediction_market_agent_tooling.markets.omen.omen import OmenAgentMarket
from prediction_market_agent_tooling.markets.omen.omen_subgraph_handler import (
    OmenSubgraphHandler,
)
from prediction_market_agent_tooling.tools.balances import get_balances
from prediction_market_agent_tooling.tools.utils import utcnow
from prediction_market_agent_tooling.tools.web3_utils import private_key_to_public_key


def sell_all(
    closing_later_than_days: int = typer.Option(7),
    from_private_key: str = typer.Option(),
    safe_address: str = typer.Option(default=None),
    auto_withdraw: bool = typer.Option(False),
) -> None:
    """
    Helper script to sell all existing outcomes on Omen that would resolve later than in X days.

    ```bash
    python scripts/sell_all_omen.py \
        --from-private-key your-private-key 
    ```
    """
    private_key = private_key_type(from_private_key)
    safe_address_checksummed = (
        Web3.to_checksum_address(safe_address) if safe_address else None
    )
    better_address = (
        safe_address_checksummed
        if safe_address_checksummed
        else private_key_to_public_key(private_key)
    )
    api_keys = APIKeys(
        BET_FROM_PRIVATE_KEY=private_key,
        SAFE_ADDRESS=safe_address_checksummed,
    )

    bets = OmenSubgraphHandler().get_bets(
        better_address=better_address,
        market_opening_after=utcnow() + timedelta(days=closing_later_than_days),
    )
    bets_total_usd = sum(b.collateralAmountUSD for b in bets)
    unique_market_urls = set(b.fpmm.url for b in bets)
    starting_balance = get_balances(better_address)
    new_balance = starting_balance  # initialisation

    logger.info(
        f"For {better_address}, found the following {len(bets)} bets on {len(unique_market_urls)} unique markets worth of {bets_total_usd} USD: {unique_market_urls}"
    )

    for bet in bets:
        agent_market = OmenAgentMarket.from_data_model(bet.fpmm)
        outcome = agent_market.outcomes[bet.outcomeIndex]
        current_token_balance = agent_market.get_token_balance(better_address, outcome)

        minimum_token_amount_for_selling = MINIMUM_BET_OMEN
        if current_token_balance.amount <= minimum_token_amount_for_selling.amount:
            logger.info(
                f"Skipping bet on {bet.fpmm.url} because the actual balance is unreasonably low {current_token_balance.amount}."
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


if __name__ == "__main__":
    typer.run(sell_all)
