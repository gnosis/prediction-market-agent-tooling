import typer

from prediction_market_agent_tooling.gtypes import private_key_type, xdai_type
from prediction_market_agent_tooling.markets.agent_market import MarketType
from prediction_market_agent_tooling.markets.omen.omen_replicate import (
    omen_replicate_from_tx,
)


def main(
    market_type: MarketType = typer.Option(),
    n: int = typer.Option(),
    initial_funds: str = typer.Option(),
    from_private_key: str = typer.Option(),
    auto_deposit: bool = True,
) -> None:
    """
    Helper script to replicate markets to omen from others.

    ```bash
    python scripts/replicate_to_omen.py \
        --market-source manifold \
        --n 5 \
        --initial-funds 0.01 \
        --from-address your-address \
        --from-private-key your-private-key
    ```
    """
    omen_replicate_from_tx(
        market_type=market_type,
        n_to_replicate=n,
        initial_funds=xdai_type(initial_funds),
        from_private_key=private_key_type(from_private_key),
        auto_deposit=auto_deposit,
    )


if __name__ == "__main__":
    typer.run(main)
