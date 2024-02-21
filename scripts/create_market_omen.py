import typer
from datetime import datetime
from prediction_market_agent_tooling.gtypes import PrivateKey, xdai_type
from prediction_market_agent_tooling.markets.omen import (
    OMEN_DEFAULT_MARKET_FEE,
    omen_create_market_tx,
    OMEN_TRUE_OUTCOME,
    OMEN_FALSE_OUTCOME,
)
from prediction_market_agent_tooling.tools.web3_utils import verify_address

app = typer.Typer()


def main(
    question: str = typer.Option(),
    closing_time: datetime = typer.Option(),
    category: str = typer.Option(),
    initial_funds: str = typer.Option(),
    from_address: str = typer.Option(),
    from_private_key: str = typer.Option(),
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
    market_address = omen_create_market_tx(
        initial_funds=xdai_type(initial_funds),
        fee=fee,
        question=question,
        closing_time=closing_time,
        category=category,
        language=language,
        from_address=verify_address(from_address),
        from_private_key=PrivateKey(from_private_key),
        outcomes=outcomes,
        auto_deposit=auto_deposit,
    )
    print(f"Market created at address: {market_address}")


if __name__ == "__main__":
    typer.run(main)
