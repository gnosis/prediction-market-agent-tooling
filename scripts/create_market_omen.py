from datetime import datetime

import typer
from web3 import Web3

from prediction_market_agent_tooling.config import APIKeys
from prediction_market_agent_tooling.gtypes import xdai_type
from prediction_market_agent_tooling.loggers import logger
from prediction_market_agent_tooling.markets.omen.data_models import (
    OMEN_FALSE_OUTCOME,
    OMEN_TRUE_OUTCOME,
)
from prediction_market_agent_tooling.markets.omen.omen import omen_create_market_tx
from prediction_market_agent_tooling.markets.omen.omen_contracts import (
    OMEN_DEFAULT_MARKET_FEE,
)


def main(
    question: str = typer.Option(),
    closing_time: datetime = typer.Option(),
    category: str = typer.Option(),
    initial_funds: str = typer.Option(),
    from_private_key: str = typer.Option(),
    safe_address: str = typer.Option(None),
    fee: float = typer.Option(OMEN_DEFAULT_MARKET_FEE),
    language: str = typer.Option("en"),
    outcomes: list[str] = typer.Option([OMEN_TRUE_OUTCOME, OMEN_FALSE_OUTCOME]),
    auto_deposit: bool = typer.Option(False),
) -> None:
    """
    Helper script to create a market on Omen, usage:

    ```bash
    python scripts/create_market_omen.py \
        --question "Will GNO reach $500 by the end of the 2024?" \
        --closing-time "2024-12-31T23:59:59" \
        --category cryptocurrency \
        --initial-funds 0.01 \
        --from-address your-address \
        --from-private-key your-private-key
    ```

    Market can be created also on the web: https://aiomen.eth.limo/#/create
    """
    safe_address_checksum = (
        Web3.to_checksum_address(safe_address) if safe_address else None
    )
    market_address = omen_create_market_tx(
        api_keys=APIKeys(),
        initial_funds=xdai_type(initial_funds),
        fee=fee,
        question=question,
        closing_time=closing_time,
        category=category,
        language=language,
        outcomes=outcomes,
        auto_deposit=auto_deposit,
    )
    logger.info(f"Market created at address: {market_address}")


if __name__ == "__main__":
    typer.run(main)
