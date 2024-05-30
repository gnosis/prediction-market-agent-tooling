from datetime import timedelta

import typer
from web3 import Web3

from prediction_market_agent_tooling.config import APIKeys
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
    balances_before = get_balances(better_address)

    logger.info(
        f"For {better_address}, found the following {len(bets)} bets on {len(unique_market_urls)} unique markets worth of {bets_total_usd} USD: {unique_market_urls}"
    )

    for bet in bets:
        agent_market = OmenAgentMarket.from_data_model(bet.fpmm)
        outcome = agent_market.outcomes[bet.outcomeIndex]
        current_token_balance = agent_market.get_token_balance(better_address, outcome)

        if current_token_balance.amount <= 0:
            logger.info(
                f"Skipping bet on {bet.fpmm.url} because the actual balance is {current_token_balance.amount}."
            )
            continue

        # TODO: This should be fixable once https://github.com/gnosis/prediction-market-agent-tooling/issues/195 is resolved and used in this script.
        # We need to convert `current_token_balance.amount` properly into their actual xDai value and then use it here.
        # Afterwards, we can sell the actual xDai value, instead of just trying to sell these hard-coded values.
        for current_xdai_value in [1.0, 0.9, 0.8, 0.7, 0.6, 0.5, 0.4, 0.3, 0.2, 0.1]:
            current_token_balance.amount = current_xdai_value

            try:
                agent_market.sell_tokens(
                    bet.boolean_outcome,
                    current_token_balance,
                    auto_withdraw=auto_withdraw,
                    api_keys=api_keys,
                )
                logger.info(
                    f"Sold bet on {bet.fpmm.url} for {current_xdai_value} xDai."
                )
                break
            except Exception as e:
                # subtraction error is currently expected because of the TODO above, so log only other errors
                if "Reverted SafeMath: subtraction overflow" not in str(e):
                    logger.error(
                        f"Failed to sell bet on {bet.fpmm.url} for {current_xdai_value} xDai because of {e}."
                    )
                continue
        else:
            logger.warning(
                f"Skipped bet on {bet.fpmm.url} because of insufficient balance."
            )

    balances_after = get_balances(better_address)
    logger.info(f"Obtained back {balances_after.wxdai - balances_before.wxdai} wxDai.")


if __name__ == "__main__":
    typer.run(sell_all)
