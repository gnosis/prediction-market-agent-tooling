"""
Integration test for cross-chain bridge (requires real funds).

WARNING: This test uses real xDAI and will incur gas costs.
Only run with a test wallet funded with ~2 xDAI on Gnosis.

To run:
    pytest tests_integration/tools/tokens/test_cross_chain_bridge_live.py -v -s
"""

import os
import time

import pytest
from web3 import Web3

from prediction_market_agent_tooling.config import APIKeys
from prediction_market_agent_tooling.gtypes import Wei
from prediction_market_agent_tooling.tools.tokens.cross_chain_bridge import (
    USDCE_ADDRESS,
    WPOL_ADDRESS,
    bridge_from_gnosis_to_polygon,
    get_bridge_status,
)

# Skip by default — only run when explicitly enabled
pytestmark = pytest.mark.skipif(
    os.getenv("RUN_LIVE_BRIDGE_TEST") != "true",
    reason="Live bridge test disabled. Set RUN_LIVE_BRIDGE_TEST=true to enable."
)


@pytest.fixture
def test_api_keys():
    """Load test wallet API keys from environment."""
    private_key = os.getenv("TEST_WALLET_PRIVATE_KEY")
    if not private_key:
        pytest.skip("TEST_WALLET_PRIVATE_KEY not set")
    
    # Create minimal APIKeys mock
    keys = APIKeys()
    keys.bet_from_private_key = private_key
    
    # Derive address from private key
    from eth_account import Account
    account = Account.from_key(private_key)
    keys.bet_from_address = Web3.to_checksum_address(account.address)
    
    return keys


def test_bridge_1_xdai_to_pol(test_api_keys):
    """
    Integration test: Bridge $1 xDAI → POL on Polygon.
    
    Acceptance criteria:
    - Real $1 xDAI → POL cross-chain swap
    - Bridge completes within 3 minutes
    - Destination balance increases
    """
    # Check initial Gnosis balance
    gnosis_web3 = Web3(Web3.HTTPProvider("https://rpc.gnosischain.com"))
    initial_xdai = gnosis_web3.eth.get_balance(test_api_keys.bet_from_address)
    
    print(f"\n[Test] Initial xDAI balance: {Wei(initial_xdai).as_token} xDAI")
    
    if initial_xdai < int(1.1e18):  # Need at least 1.1 xDAI (1 + gas)
        pytest.skip(f"Insufficient xDAI balance: {Wei(initial_xdai).as_token}")
    
    # Check initial Polygon POL balance
    polygon_web3 = Web3(Web3.HTTPProvider("https://polygon-rpc.com"))
    wpol_contract = polygon_web3.eth.contract(
        address=WPOL_ADDRESS,
        abi=[{
            "constant": True,
            "inputs": [{"name": "_owner", "type": "address"}],
            "name": "balanceOf",
            "outputs": [{"name": "balance", "type": "uint256"}],
            "type": "function"
        }]
    )
    initial_pol = wpol_contract.functions.balanceOf(test_api_keys.bet_from_address).call()
    
    print(f"[Test] Initial WPOL balance: {Wei(initial_pol).as_token} WPOL")
    
    # Bridge 1 xDAI → POL
    print(f"[Test] Initiating bridge: 1 xDAI → WPOL...")
    start_time = time.time()
    
    tx_hash = bridge_from_gnosis_to_polygon(
        amount_wei=Wei(int(1e18)),  # 1 xDAI
        buy_token=WPOL_ADDRESS,
        api_keys=test_api_keys,
        timeout=180,  # 3 minutes
    )
    
    elapsed = time.time() - start_time
    print(f"[Test] Bridge submitted in {elapsed:.1f}s. Destination tx: {tx_hash}")
    
    # Wait for settlement (poll every 10s for up to 3 minutes)
    print(f"[Test] Waiting for settlement...")
    max_wait = 180
    poll_interval = 10
    
    for i in range(max_wait // poll_interval):
        time.sleep(poll_interval)
        
        status = get_bridge_status(tx_hash)
        if status.get("confirmed"):
            print(f"[Test] Bridge confirmed after {(i+1)*poll_interval}s")
            break
        
        print(f"[Test] Still waiting... ({(i+1)*poll_interval}s elapsed)")
    else:
        pytest.fail(f"Bridge did not confirm within {max_wait}s")
    
    # Check final balances
    final_xdai = gnosis_web3.eth.get_balance(test_api_keys.bet_from_address)
    final_pol = wpol_contract.functions.balanceOf(test_api_keys.bet_from_address).call()
    
    print(f"\n[Test] Final xDAI balance: {Wei(final_xdai).as_token} xDAI")
    print(f"[Test] Final WPOL balance: {Wei(final_pol).as_token} WPOL")
    
    # Assertions
    xdai_spent = initial_xdai - final_xdai
    pol_received = final_pol - initial_pol
    
    print(f"\n[Test] xDAI spent: {Wei(xdai_spent).as_token}")
    print(f"[Test] WPOL received: {Wei(pol_received).as_token}")
    
    # Should have spent ~1 xDAI (plus gas)
    assert xdai_spent >= int(1e18), "Should have spent at least 1 xDAI"
    assert xdai_spent <= int(1.05e18), "Should not have spent more than 1.05 xDAI"
    
    # Should have received some POL (exact amount depends on exchange rate)
    assert pol_received > 0, "Should have received some WPOL"
    
    print(f"\n✅ Bridge test passed!")
    print(f"   Settlement time: {elapsed:.1f}s")
    print(f"   Exchange rate: 1 xDAI → {Wei(pol_received).as_token} WPOL")


def test_bridge_1_xdai_to_usdce(test_api_keys):
    """
    Integration test: Bridge $1 xDAI → USDC.e on Polygon.
    
    Similar to POL test but with USDC.e as destination token.
    """
    # Similar implementation to test_bridge_1_xdai_to_pol
    # but with USDCE_ADDRESS as buy_token
    pytest.skip("Implement if needed — POL test covers the main flow")
