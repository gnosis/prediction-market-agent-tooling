import datetime

import typer
from web3 import Web3

from prediction_market_agent_tooling.config import APIKeys
from prediction_market_agent_tooling.gtypes import (
    OutcomeStr,
    private_key_type,
    CollateralToken,
)
from prediction_market_agent_tooling.loggers import logger
from prediction_market_agent_tooling.markets.omen.data_models import (
    OMEN_BINARY_MARKET_OUTCOMES,
)
from prediction_market_agent_tooling.markets.omen.omen import omen_create_market_tx
from prediction_market_agent_tooling.markets.omen.omen_contracts import (
    OMEN_DEFAULT_MARKET_FEE_PERC,
)
from prediction_market_agent_tooling.tools.utils import DatetimeUTC


def main(
    safe_address: str = typer.Option(None),
    # cl_token: CollateralTokenChoice = CollateralTokenChoice.sdai,
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
    w3 = Web3(Web3.HTTPProvider("http://localhost:8545"))
    safe_address_checksum = (
        Web3.to_checksum_address(safe_address) if safe_address else None
    )
    from_private_key = (
        "0xac0974bec39a17e36ba4a6b4d238ff944bacb478cbed5efcae784d7bf4f2ff80"  # anvil1
    )
    api_keys = APIKeys(
        BET_FROM_PRIVATE_KEY=private_key_type(from_private_key),
        SAFE_ADDRESS=safe_address_checksum,
    )
    # parameters
    closing_time = DatetimeUTC.now() + datetime.timedelta(days=1)
    cl_token = Web3.to_checksum_address("0xDF3DA9c97F5DB9B89dce95A05B1e2a04a00A59D3")
    initial_funds_usd = 0.01
    question = "Test market 1"
    category = "cryptocurrency"

    market = omen_create_market_tx(
        api_keys=api_keys,
        # collateral_token_address=COLLATERAL_TOKEN_CHOICE_TO_ADDRESS[cl_token],
        collateral_token_address=cl_token,
        initial_funds=CollateralToken(initial_funds_usd),
        fee_perc=fee_perc,
        question=question,
        closing_time=closing_time,
        category=category,
        language=language,
        outcomes=[OutcomeStr(x) for x in outcomes],
        auto_deposit=auto_deposit,
        web3=w3,
    )
    logger.info(f"Market created: {market}")


if __name__ == "__main__":
    typer.run(main)
