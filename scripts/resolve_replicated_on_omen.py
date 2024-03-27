import typer
from loguru import logger

from prediction_market_agent_tooling.gtypes import private_key_type
from prediction_market_agent_tooling.markets.omen.omen_resolve_replicated import (
    omen_resolve_all_markets_based_on_others_tx,
)


def main(
    from_private_key: str = typer.Option(),
) -> None:
    """
    Helper script to resolve markets on Omen that were replicated by the replication function.

    ```bash
    python scripts/resolve_replicated_on_omen.py --from-private-key your-private-key
    ```
    """
    resolved_addresses = omen_resolve_all_markets_based_on_others_tx(
        from_private_key=private_key_type(from_private_key),
    )
    logger.info(f"Resolved markets: {resolved_addresses}")


if __name__ == "__main__":
    typer.run(main)
