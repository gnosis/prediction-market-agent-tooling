from datetime import datetime

import typer
from web3 import Web3

from prediction_market_agent_tooling.config import APIKeys
from prediction_market_agent_tooling.gtypes import private_key_type, xdai_type, xDai
from prediction_market_agent_tooling.loggers import logger
from prediction_market_agent_tooling.markets.omen.data_models import (
    OMEN_BINARY_MARKET_OUTCOMES,
)
from prediction_market_agent_tooling.markets.seer.seer import seer_create_market_tx
from prediction_market_agent_tooling.tools.utils import DatetimeUTC


def main(
    question: str = typer.Option(),
    opening_time: datetime = typer.Option(),
    category: str = typer.Option(),
    initial_funds: str = typer.Option(),
    from_private_key: str = typer.Option(),
    safe_address: str = typer.Option(None),
    min_bond_xdai: xDai = typer.Option(xdai_type(10)),
    language: str = typer.Option("en"),
    outcomes: list[str] = typer.Option(OMEN_BINARY_MARKET_OUTCOMES),
    auto_deposit: bool = typer.Option(False),
) -> None:
    """
    Helper script to create a market on Omen, usage:

    ```bash
    python scripts/create_market_seer.py \
        --question "Will GNO reach $500 by the end of the 2024?" \
        --opening_time "2024-12-31T23:59:59" \
        --category cryptocurrency \
        --initial-funds 0.01 \
        --from-private-key your-private-key
    ```
    """
    safe_address_checksum = (
        Web3.to_checksum_address(safe_address) if safe_address else None
    )
    api_keys = APIKeys(
        BET_FROM_PRIVATE_KEY=private_key_type(from_private_key),
        SAFE_ADDRESS=safe_address_checksum,
    )
    market = seer_create_market_tx(
        api_keys=api_keys,
        initial_funds=xdai_type(initial_funds),
        question=question,
        opening_time=DatetimeUTC.from_datetime(opening_time),
        category=category,
        language=language,
        outcomes=outcomes,
        auto_deposit=auto_deposit,
        min_bond_xdai=min_bond_xdai,
    )
    logger.info(f"Market created: {market}")


if __name__ == "__main__":
    typer.run(main)
