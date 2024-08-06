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
