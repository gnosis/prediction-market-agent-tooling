from ape_test.accounts import TestAccount
from eth_account import Account
from web3 import Web3
from web3.middleware import ExtraDataToPOAMiddleware

from prediction_market_agent_tooling.config import RPCConfig, APIKeys
from prediction_market_agent_tooling.gtypes import xDai
from prediction_market_agent_tooling.markets.polymarket.constants import (
    CTF_EXCHANGE_POLYMARKET,
)
from prediction_market_agent_tooling.markets.polymarket.polymarket_contracts import (
    PolymarketConditionalTokenContract,
)
from prediction_market_agent_tooling.tools.utils import check_not_none


def test_is_approved_for_all(eoa_accounts: list[TestAccount]) -> None:
    owner = eoa_accounts[0]
    # ToDo - Create new ape-foundry config for Polygon
    c = PolymarketConditionalTokenContract()
    web3 = Web3(Web3.HTTPProvider(check_not_none(RPCConfig().polygon_rpc_url)))
    is_approved = c.isApprovedForAll(
        owner=owner.address, for_address=CTF_EXCHANGE_POLYMARKET, web3=web3
    )
    assert not is_approved


def test_set_approval_for_all(test_keys: APIKeys) -> None:
    # owner = eoa_accounts[0]
    # from foundry
    owner = Account.from_key(
        "0xac0974bec39a17e36ba4a6b4d238ff944bacb478cbed5efcae784d7bf4f2ff80"
    )
    # ToDo - Create new ape-foundry config for Polygon
    c = PolymarketConditionalTokenContract()
    w3 = Web3(Web3.HTTPProvider("http://localhost:8546"))

    w3.provider.make_request(
        "anvil_setBalance", [test_keys.public_key, hex(xDai(1).as_xdai_wei.value)]
    )

    # Inject the PoA middleware. This is the crucial step to resolve the ExtraDataLengthError.
    # It should be injected in the first position (index 0).
    w3.middleware_onion.inject(ExtraDataToPOAMiddleware, layer=0)

    c.setApprovalForAll(
        api_keys=test_keys,
        for_address=CTF_EXCHANGE_POLYMARKET,
        approve=True,
        web3=w3,
    )
    is_approved = c.isApprovedForAll(
        owner=owner.address, for_address=CTF_EXCHANGE_POLYMARKET, web3=w3
    )
    assert is_approved
