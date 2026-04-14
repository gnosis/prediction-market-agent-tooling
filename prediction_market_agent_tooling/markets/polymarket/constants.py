from web3 import Web3

from prediction_market_agent_tooling.gtypes import USD

# Contract addresses
CTF_EXCHANGE_POLYMARKET = Web3.to_checksum_address(
    "0x4bfb41d5b3570defd03c39a9a4d8de6bd8b8982e"
)
NEG_RISK_EXCHANGE = Web3.to_checksum_address(
    "0xC5d563A36AE78145C45a50134d48A1215220f80a"
)
NEG_RISK_ADAPTER = Web3.to_checksum_address(
    "0xd91E80cF2E7be2e162c6513ceD06f1dD0dA35296"
)
# Aave V3 static (ERC-4626) wrapper over the aToken for USDC native on Polygon.
# Non-rebasing — yield accrues via share-price appreciation, which is what
# CTF splitPosition requires (rebasing aTokens would "freeze" yield at mint).
STATA_POL_USDCN_ADDRESS = Web3.to_checksum_address(
    "0x2DCA80061632f3F87c9cA28364d1d0c30cD79a19"
)

# API URLs
POLYMARKET_BASE_URL = "https://polymarket.com"
POLYMARKET_GAMMA_API_BASE_URL = "https://gamma-api.polymarket.com/"
POLYMARKET_DATA_API_BASE_URL = "https://data-api.polymarket.com"
POLYMARKET_CLOB_API_URL = "https://clob.polymarket.com"
POLYMARKET_CONDITIONS_SUBGRAPH_URL = "https://gateway.thegraph.com/api/{graph_api_key}/subgraphs/id/81Dm16JjuFSrqz813HysXoUPvzTwE7fsfPk2RTf66nyC"

# Trading constants
MARKETS_LIMIT = 100
TRADES_LIMIT = 100
POLYMARKET_TINY_BET_AMOUNT = USD(1.0)
POLYMARKET_MIN_LIQUIDITY_USD = USD(5)
