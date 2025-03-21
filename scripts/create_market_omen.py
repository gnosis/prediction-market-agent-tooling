from datetime import datetime

import typer
from web3 import Web3

from prediction_market_agent_tooling.config import APIKeys
from prediction_market_agent_tooling.gtypes import USD, OutcomeStr, private_key_type
from prediction_market_agent_tooling.loggers import logger
from prediction_market_agent_tooling.markets.omen.data_models import (
    OMEN_BINARY_MARKET_OUTCOMES,
)
from prediction_market_agent_tooling.markets.omen.omen import omen_create_market_tx
from prediction_market_agent_tooling.markets.omen.omen_contracts import (
    COLLATERAL_TOKEN_CHOICE_TO_ADDRESS,
    OMEN_DEFAULT_MARKET_FEE_PERC,
    CollateralTokenChoice,
)
from prediction_market_agent_tooling.tools.utils import DatetimeUTC


def main(
    question: str = typer.Option(),
    closing_time: datetime = typer.Option(),
    category: str = typer.Option(),
    initial_funds_usd: str = typer.Option(),
    from_private_key: str = typer.Option(),
    safe_address: str = typer.Option(None),
    cl_token: CollateralTokenChoice = CollateralTokenChoice.sdai,
    fee_perc: float = typer.Option(OMEN_DEFAULT_MARKET_FEE_PERC),
    language: str = typer.Option("en"),
    outcomes: list[str] = typer.Option(OMEN_BINARY_MARKET_OUTCOMES),
    auto_deposit: bool = typer.Option(True),
) -> None:
    """
    Helper script to create a market on Omen, usage:

    ```bash
    python scripts/create_market_omen.py \
        --question "Will GNO reach $500 by the end of the 2024?" \
        --closing-time "2024-12-31T23:59:59" \
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
    market = omen_create_market_tx(
        api_keys=api_keys,
        collateral_token_address=COLLATERAL_TOKEN_CHOICE_TO_ADDRESS[cl_token],
        initial_funds=USD(initial_funds_usd),
        fee_perc=fee_perc,
        question=question,
        closing_time=DatetimeUTC.from_datetime(closing_time),
        category=category,
        language=language,
        outcomes=[OutcomeStr(x) for x in outcomes],
        auto_deposit=auto_deposit,
    )
    logger.info(f"Market created: {market}")


if __name__ == "__main__":
    typer.run(main)
