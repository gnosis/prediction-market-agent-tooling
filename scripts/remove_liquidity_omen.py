import typer
from web3 import Web3

from prediction_market_agent_tooling.config import APIKeys
from prediction_market_agent_tooling.gtypes import private_key_type
from prediction_market_agent_tooling.loggers import logger
from prediction_market_agent_tooling.markets.omen.omen import (
    OmenAgentMarket,
    omen_remove_fund_market_tx,
)
from prediction_market_agent_tooling.markets.omen.omen_subgraph_handler import (
    OmenSubgraphHandler,
)


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
    market = OmenAgentMarket.from_data_model(
        OmenSubgraphHandler().get_omen_market_by_market_id(
            Web3.to_checksum_address(market_id)
        )
    )
    omen_remove_fund_market_tx(api_keys=api_keys, market=market, shares=None)
    logger.info(f"Liquidity removed from: {market_id}")


if __name__ == "__main__":
    typer.run(main)
