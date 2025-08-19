from web3 import Web3

from prediction_market_agent_tooling.gtypes import USD

CTF_EXCHANGE_POLYMARKET = Web3.to_checksum_address(
    "0x4bfb41d5b3570defd03c39a9a4d8de6bd8b8982e"
)
NEG_RISK_EXCHANGE = Web3.to_checksum_address(
    "0xC5d563A36AE78145C45a50134d48A1215220f80a"
)
NEG_RISK_ADAPTER = Web3.to_checksum_address(
    "0xd91E80cF2E7be2e162c6513ceD06f1dD0dA35296"
)
# We reference this value in multiple files
POLYMARKET_TINY_BET_AMOUNT = USD(1.0)
