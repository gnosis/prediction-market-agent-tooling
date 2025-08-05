from web3 import Web3
from web3.types import RPCEndpoint

from prediction_market_agent_tooling.config import APIKeys
from prediction_market_agent_tooling.gtypes import xDai
from prediction_market_agent_tooling.markets.polymarket.constants import (
    CTF_EXCHANGE_POLYMARKET,
)
from prediction_market_agent_tooling.markets.polymarket.polymarket_contracts import (
    PolymarketConditionalTokenContract,
)


def test_set_approval_for_all(test_keys: APIKeys, polygon_local_web3: Web3) -> None:
    c = PolymarketConditionalTokenContract()
    polygon_local_web3.provider.make_request(
        RPCEndpoint("anvil_setBalance"),
        [test_keys.public_key, hex(xDai(1).as_xdai_wei.value)],
    )

    c.setApprovalForAll(
        api_keys=test_keys,
        for_address=CTF_EXCHANGE_POLYMARKET,
        approve=True,
        web3=polygon_local_web3,
    )
    is_approved = c.isApprovedForAll(
        owner=test_keys.public_key,
        for_address=CTF_EXCHANGE_POLYMARKET,
        web3=polygon_local_web3,
    )
    assert is_approved
