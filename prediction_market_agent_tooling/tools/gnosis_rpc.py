import os

from prediction_market_agent_tooling.gtypes import ChainID

GNOSIS_NETWORK_ID = ChainID(100)  # xDai network.
GNOSIS_RPC_URL = os.getenv("GNOSIS_RPC_URL", "https://gnosis-rpc.publicnode.com")
