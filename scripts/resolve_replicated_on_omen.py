from pprint import pprint

import typer

from prediction_market_agent_tooling.gtypes import private_key_type
from prediction_market_agent_tooling.markets.omen.omen_resolve_replicated import (
    omen_finalize_and_resolve_all_markets_based_on_others_tx,
)

# Use without the pretty exceptions, because they make the error stack unusable here.
app = typer.Typer(pretty_exceptions_show_locals=False)


@app.command()
def main(
    from_private_key: str = typer.Option(),
) -> None:
    """
    Helper script to resolve markets on Omen that were replicated by the replication function.

    ```bash
    python scripts/resolve_replicated_on_omen.py --from-private-key your-private-key
    ```
    """
    result = omen_finalize_and_resolve_all_markets_based_on_others_tx(
        from_private_key=private_key_type(from_private_key),
    )
    pprint(result.model_dump())


if __name__ == "__main__":
    app()
