from unittest import mock

import pytest
from ape import Contract
from ape import accounts as AccountManagerApe
from web3 import Web3

from prediction_market_agent_tooling.config import APIKeys, RPCConfig
from prediction_market_agent_tooling.gtypes import USD, Wei, private_key_type, xDai
from prediction_market_agent_tooling.markets.polymarket.polymarket import (
    PolymarketAgentMarket,
)
from prediction_market_agent_tooling.markets.polymarket.polymarket_contracts import (
    USDCeContract,
)
from prediction_market_agent_tooling.tools.hexbytes_custom import HexBytes
from tests_integration_with_local_chain.conftest import create_and_fund_random_account

# Known USDC whale on Polygon (Wormhole token bridge)
USDC_WHALE = Web3.to_checksum_address("0x5a58505a96D1dbf8dF91cB21B54419FC36e93fdE")

MOCK_TX_HASH = HexBytes(
    "0xabc123def456abc123def456abc123def456abc123def456abc123def456abc1"  # web3-private-key-ok
)


def _fund_account_with_usdc(
    api_keys: APIKeys, usdc_amount_wei: Wei, polygon_local_web3: Web3
) -> None:
    """Transfer USDC from a whale to the test account on the local fork."""
    with AccountManagerApe.use_sender(USDC_WHALE):
        usdc = USDCeContract()
        contract = Contract(address=usdc.address, abi=usdc.abi)
        contract.transfer(api_keys.bet_from_address, usdc_amount_wei.value)


def _create_funded_account(
    polygon_local_web3: Web3, usdc_amount: float = 5.0
) -> APIKeys:
    """Create a fresh account funded with POL (gas) and USDC."""
    fresh_account = create_and_fund_random_account(
        web3=polygon_local_web3,
        deposit_amount=xDai(10),  # POL for gas
    )
    api_keys = APIKeys(
        BET_FROM_PRIVATE_KEY=private_key_type(fresh_account.key.hex()),
        SAFE_ADDRESS=None,
    )
    usdc_wei = Wei(int(usdc_amount * 1e6))
    _fund_account_with_usdc(api_keys, usdc_wei, polygon_local_web3)
    return api_keys


def test_get_user_balance_local_chain(polygon_local_web3: Web3) -> None:
    """Verify get_user_balance reads correct USDC balance from a local Polygon fork."""
    api_keys = _create_funded_account(polygon_local_web3, usdc_amount=5.0)

    # get_user_balance uses RPCConfig internally, redirect to local fork
    with mock.patch.object(
        RPCConfig, "get_polygon_web3", return_value=polygon_local_web3
    ):
        balance = PolymarketAgentMarket.get_user_balance(str(api_keys.bet_from_address))

    assert balance > 0
    assert balance == pytest.approx(5.0, abs=0.01)


def test_get_trade_balance_local_chain(polygon_local_web3: Web3) -> None:
    """Verify get_trade_balance reads correct USDC balance from a local Polygon fork."""
    api_keys = _create_funded_account(polygon_local_web3, usdc_amount=10.0)

    trade_balance = PolymarketAgentMarket.get_trade_balance(
        api_keys=api_keys, web3=polygon_local_web3
    )

    assert trade_balance >= USD(0)
    assert trade_balance.value == pytest.approx(10.0, abs=0.01)


def test_place_bet_local_chain(polygon_local_web3: Web3) -> None:
    """Test full place_bet flow on a local Polygon fork.

    Everything runs on-chain (funding, approvals) except the CLOB API HTTP calls
    which are mocked. This validates:
    - Account funding with USDC
    - ClobManager approval setup on-chain
    - Token ID resolution from a real market
    - Order creation data flow
    """
    api_keys = _create_funded_account(polygon_local_web3, usdc_amount=5.0)

    # Fetch a real open market from Polymarket API
    markets = PolymarketAgentMarket.get_markets(limit=1)
    assert len(markets) > 0, "No open markets found on Polymarket"
    market = markets[0]

    mock_order_result = {
        "errorMsg": "",
        "orderID": "test-order-1",
        "transactionsHashes": [MOCK_TX_HASH.to_0x_hex()],
        "status": "matched",
        "success": True,
    }

    # Redirect RPCConfig.get_polygon_web3 to our local fork, so ClobManager's
    # __init_approvals runs against the fork (not mainnet).
    # Mock only the ClobClient HTTP calls — everything else runs for real.
    with (
        mock.patch.object(
            RPCConfig, "get_polygon_web3", return_value=polygon_local_web3
        ),
        mock.patch(
            "prediction_market_agent_tooling.markets.polymarket.clob_manager.ClobClient"
        ) as mock_clob_client_cls,
        mock.patch(
            "prediction_market_agent_tooling.markets.polymarket.polymarket.APIKeys",
            return_value=api_keys,
        ),
    ):
        mock_clob_client = mock_clob_client_cls.return_value
        mock_clob_client.create_or_derive_api_creds.return_value = {}
        mock_clob_client.set_api_creds.return_value = None
        mock_clob_client.create_market_order.return_value = {"mock": "signed_order"}
        mock_clob_client.post_order.return_value = mock_order_result

        # Mock on-chain verification since the tx hash is fake
        mock_receipt = {"status": 1}
        polygon_local_web3.eth.get_transaction_receipt = mock.MagicMock(  # type: ignore[method-assign]
            return_value=mock_receipt
        )

        tx_hash = market.place_bet(
            outcome=market.outcomes[0],
            amount=USD(2),
        )

        assert tx_hash == MOCK_TX_HASH.to_0x_hex()

        # Verify ClobClient received correct token_id
        expected_token_id = market.get_token_id_for_outcome(market.outcomes[0])
        call_args = mock_clob_client.create_market_order.call_args
        order_args = call_args[0][0]
        assert order_args.token_id == str(expected_token_id)
        assert order_args.amount == 2.0
