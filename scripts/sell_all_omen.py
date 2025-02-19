import typer
from web3 import Web3

from prediction_market_agent_tooling.config import APIKeys
from prediction_market_agent_tooling.gtypes import private_key_type
from prediction_market_agent_tooling.tools.omen.sell_positions import sell_all


def main(
    from_private_key: str,
    closing_later_than_days: int = 7,
    safe_address: str | None = None,
    auto_withdraw: bool = False,
) -> None:
    """
    Helper script to sell all existing outcomes on Omen that would resolve later than in X days.

    ```bash
    python scripts/sell_all_omen.py your-private-key
    ```
    """
    api_keys = APIKeys(
        BET_FROM_PRIVATE_KEY=private_key_type(from_private_key),
        SAFE_ADDRESS=Web3.to_checksum_address(safe_address) if safe_address else None,
    )
    sell_all(api_keys, closing_later_than_days, auto_withdraw)


if __name__ == "__main__":
    typer.run(main)
