from web3 import Web3

from prediction_market_agent_tooling.deploy.agent_example import DeployableCoinFlipAgent
# os.environ[
#     "GNOSIS_RPC_URL"
# ] = "https://virtual.gnosis.rpc.tenderly.co/334593e6-c7c6-4e15-a4da-02c33ed0d1f8"
from prediction_market_agent_tooling.markets.markets import MarketType

if __name__ == "__main__":
    from prediction_market_agent_tooling.markets.omen.omen_subgraph_handler import (
        OmenSubgraphHandler,
    )

    subgraph_handler = OmenSubgraphHandler()
    market_id = Web3.to_checksum_address("0x065e4580145a550669601b004962f85570651da9")
    market = subgraph_handler.get_omen_market_by_market_id(market_id)
    d = DeployableCoinFlipAgent()
    d.run(market_type=MarketType.OMEN)
