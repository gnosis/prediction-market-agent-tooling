from datetime import datetime

import typer
from web3 import Web3

from prediction_market_agent_tooling.config import APIKeys
from prediction_market_agent_tooling.gtypes import private_key_type, xdai_type
from prediction_market_agent_tooling.loggers import logger
from prediction_market_agent_tooling.markets.omen.data_models import (
    OMEN_BINARY_MARKET_OUTCOMES,
)
from prediction_market_agent_tooling.markets.omen.omen import (
    omen_create_market_tx,
    omen_remove_fund_market_tx,
)
from prediction_market_agent_tooling.markets.omen.omen_subgraph_handler import (
    OmenSubgraphHandler,
)
from prediction_market_agent_tooling.markets.omen.omen_contracts import (
    COLLATERAL_TOKEN_CHOICE_TO_ADDRESS,
    OMEN_DEFAULT_MARKET_FEE_PERC,
    CollateralTokenChoice,
)
from prediction_market_agent_tooling.tools.utils import DatetimeUTC


def main(
    market_id: str = typer.Option(),
    from_private_key: str = typer.Option(),
    safe_address: str = typer.Option(None),
) -> None:
    """
    Helper script to remove your liquidity from a market on Omen, usage:

    ```bash
    python scripts/remove_liquidity_omen.py \
        --market-id "0x176122ecc05d3b1364fa815f4e01ddad8a2a66bc" \
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
    market = OmenSubgraphHandler().get_omen_market_by_market_id(
        Web3.to_checksum_address(market_id)
    )
    market_address = omen_remove_fund_market_tx(
        api_keys=api_keys, market=market, shares=None
    )
    logger.info(f"Market created at address: {market_address}")


if __name__ == "__main__":
    typer.run(main)
