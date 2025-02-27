import typer
from eth_typing import HexAddress, HexStr
from web3 import Web3

from prediction_market_agent_tooling.config import APIKeys
from prediction_market_agent_tooling.gtypes import private_key_type, xdai_type
from prediction_market_agent_tooling.markets.omen.omen import (
    OmenAgentMarket,
    omen_buy_outcome_tx,
    omen_sell_outcome_tx,
)
from prediction_market_agent_tooling.markets.omen.omen_subgraph_handler import (
    OmenSubgraphHandler,
)

app = typer.Typer()


@app.command()
def buy(
    amount: str = typer.Option(),
    from_private_key: str = typer.Option(),
    safe_address: str = typer.Option(default=None),
    market_id: str = typer.Option(),
    outcome: str = typer.Option(),
    auto_deposit: bool = typer.Option(True),
) -> None:
    """
    Helper script to place a bet on Omen, usage:

    ```bash
    python scripts/bet_omen.py buy \
        --amount 0.01 \
        --from-private-key your-private-key \
        --market-id some-market-id \
        --outcome one-of-the-outcomes
    ```

    Market ID can be found easily in the URL: https://aiomen.eth.limo/#/0x86376012a5185f484ec33429cadfa00a8052d9d4
    """
    safe_address_checksum = (
        Web3.to_checksum_address(safe_address) if safe_address else None
    )
    market = build_omen_agent_market(market_id)
    omen_buy_outcome_tx(
        api_keys=APIKeys(
            SAFE_ADDRESS=safe_address_checksum,
            BET_FROM_PRIVATE_KEY=private_key_type(from_private_key),
        ),
        amount=xdai_type(amount),
        market=market,
        outcome=outcome,
        auto_deposit=auto_deposit,
    )


@app.command()
def sell(
    amount: str = typer.Option(),
    from_private_key: str = typer.Option(),
    safe_address: str = typer.Option(default=None),
    market_id: str = typer.Option(),
    outcome: str = typer.Option(),
    auto_withdraw: bool = typer.Option(True),
) -> None:
    """
    Helper script to sell outcome of an existing bet on Omen, usage:

    ```bash
    python scripts/bet_omen.py sell \
        --amount 0.01 \
        --from-private-key your-private-key \
        --market-id some-market-id \
        --outcome one-of-the-outcomes
    ```

    Market ID can be found easily in the URL: https://aiomen.eth.limo/#/0x86376012a5185f484ec33429cadfa00a8052d9d4
    """
    safe_address_checksum = (
        Web3.to_checksum_address(safe_address) if safe_address else None
    )

    market = build_omen_agent_market(market_id)
    omen_sell_outcome_tx(
        api_keys=APIKeys(
            SAFE_ADDRESS=safe_address_checksum,
            BET_FROM_PRIVATE_KEY=private_key_type(from_private_key),
        ),
        amount=xdai_type(amount),
        market=market,
        outcome=outcome,
        auto_withdraw=auto_withdraw,
    )


def build_omen_agent_market(market_id: str) -> OmenAgentMarket:
    subgraph_handler = OmenSubgraphHandler()
    market_data_model = subgraph_handler.get_omen_market_by_market_id(
        HexAddress(HexStr(market_id))
    )
    market = OmenAgentMarket.from_data_model(market_data_model)
    return market


if __name__ == "__main__":
    app()
