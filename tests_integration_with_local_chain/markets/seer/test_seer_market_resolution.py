from web3 import Web3

from prediction_market_agent_tooling.config import APIKeys
from prediction_market_agent_tooling.gtypes import HexBytes
from prediction_market_agent_tooling.markets.seer.seer import SeerAgentMarket
from prediction_market_agent_tooling.markets.seer.seer_subgraph_handler import (
    SeerSubgraphHandler,
)


def test_seer_scalar_redemption(
    seer_subgraph_handler_test: SeerSubgraphHandler,
) -> None:
    # ToDO - fork at specific block 41701049
    # ToDo - mock below (used inside redeem_winnings)
    """
    def redeem_winnings(api_keys: APIKeys) -> None:
        web3 = RPCConfig().get_web3()
    """
    w3 = Web3(
        Web3.HTTPProvider(
            "https://virtual.gnosis.eu.rpc.tenderly.co/dc2949e2-99a9-4d6c-b77a-c6488e08431c"
        )
    )

    agent_safe = Web3.to_checksum_address("0xdF99b89934f697f295fDf132Ec5174656bC088BD")
    api_keys = APIKeys(SAFE_ADDRESS=agent_safe)
    market_id = HexBytes("0x8517e637b15246d8ae0b384bf53c601a99d8b16f")
    market = seer_subgraph_handler_test.get_market_by_id(market_id=market_id)
    agent_market = SeerAgentMarket.from_data_model_with_subgraph(
        model=market, seer_subgraph=seer_subgraph_handler_test, must_have_prices=False
    )
    agent_market.redeem_winnings(api_keys=api_keys)
    print("done")
