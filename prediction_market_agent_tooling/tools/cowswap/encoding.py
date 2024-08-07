from eth_typing import ChecksumAddress
from web3 import Web3

from prediction_market_agent_tooling.gtypes import ChainID

MESSAGE_TYPES_CANCELLATION = {
    "OrderCancellations": [
        {"name": "orderUids", "type": "bytes[]"},
    ]
}

# EIP-712 Types
MESSAGE_TYPES = {
    "Order": [
        {"name": "sellToken", "type": "address"},
        {"name": "buyToken", "type": "address"},
        {"name": "receiver", "type": "address"},
        {"name": "sellAmount", "type": "uint256"},
        {"name": "buyAmount", "type": "uint256"},
        {"name": "validTo", "type": "uint32"},
        {"name": "appData", "type": "bytes32"},
        {"name": "feeAmount", "type": "uint256"},
        {"name": "kind", "type": "string"},
        {"name": "partiallyFillable", "type": "bool"},
        {"name": "sellTokenBalance", "type": "string"},
        {"name": "buyTokenBalance", "type": "string"},
    ]
}

# EIP-712 Domain
DOMAIN = {
    "name": "Gnosis Protocol",
    "version": "v2",
    "chainId": 100,  # Replace with actual chainId
    "verifyingContract": "0x9008D19f58AAbD9eD0D60971565AA8510560ab41",  # Gnosis Mainnet, from
}

# Relayer address for allowance purposes
RELAYER_ADDRESSES: dict[ChainID, ChecksumAddress] = {
    ChainID(100): Web3.to_checksum_address("0xC92E8bdf79f0507f65a392b0ab4667716BFE0110")
}
