import typer
from web3 import Web3
from web3.constants import HASH_ZERO
from web3.gas_strategies.rpc import rpc_gas_price_strategy

from prediction_market_agent_tooling.config import APIKeys
from prediction_market_agent_tooling.markets.omen.omen import (
    OmenAgentMarket,
    get_market,
)
from prediction_market_agent_tooling.markets.omen.omen_contracts import (
    OmenConditionalTokenContract,
    OmenFixedProductMarketMakerContract,
)

app = typer.Typer()


@app.command()
def buy(
    amount: str = typer.Option(),
    from_address: str = typer.Option(),
    from_private_key: str = typer.Option(),
    market_id: str = typer.Option(),
    outcome: str = typer.Option(),
    auto_deposit: bool = typer.Option(False),
) -> None:
    """
    Helper script to place a bet on Omen, usage:

    ```bash
    python scripts/bet_omen.py buy \
        --amount 0.01 \
        --from-address your-address \
        --from-private-key your-private-key \
        --market-id some-market-id \
        --outcome one-of-the-outcomes
    ```

    Market ID can be found easily in the URL: https://aiomen.eth.limo/#/0x86376012a5185f484ec33429cadfa00a8052d9d4
    """
    print("oi")
    market = OmenAgentMarket.from_data_model(get_market(market_id))
    print(f"market {market} {market.is_resolved()}")

    # ToDo - Check how much we can redeem
    # rpc_url = "https://light-distinguished-isle.xdai.quiknode.pro/398333e0cb68ee18d38f5cda5deecd5676754923/"
    # Using forked local Gnosis chain for testing
    # rpc_url = "http://127.0.0.1:8545"
    rpc_url = "https://rpc.tenderly.co/fork/000e6ff5-8ef3-4741-8aaa-022d39f81e08"
    w3 = Web3(Web3.HTTPProvider(rpc_url))
    print(w3.is_connected())
    market_contract = market.get_contract()

    market_contract: OmenFixedProductMarketMakerContract = market.get_contract()
    conditional_token_contract = OmenConditionalTokenContract()

    # Verify, that markets uses conditional tokens that we expect.
    if market_contract.conditionalTokens() != conditional_token_contract.address:
        raise ValueError(
            f"Market {market.id} uses conditional token that we didn't expect, {market_contract.conditionalTokens()} != {conditional_token_contract.address=}"
        )

    # `redeemPositions` function params:
    collateral_token_address = market.collateral_token_contract_address_checksummed
    # ToDo - No condition
    condition_id = market.condition.id
    parent_collection_id = HASH_ZERO  # Taken from Olas
    index_sets = market.condition.index_sets  # Taken from Olas

    if not market.is_resolved():
        raise RuntimeError("Cannot redeem winnings if market is not yet resolved")

    # ToDo - Add types
    w3.eth.set_gas_price_strategy(rpc_gas_price_strategy)
    keys = APIKeys()
    result = conditional_token_contract.send(
        from_address=keys.bet_from_address,
        from_private_key=keys.bet_from_private_key,
        function_name="redeemPositions",
        function_params=[
            collateral_token_address,
            parent_collection_id,
            condition_id,
            index_sets,
        ],
        web3=w3,
    )
    print(result)


if __name__ == "__main__":
    app()
