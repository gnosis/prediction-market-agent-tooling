"""
Cross-chain bridge integration for Gnosis → Polygon token swaps.

Uses CoW Protocol's bridging service to enable Polymarket agents to automatically
bridge xDAI from Gnosis when Polygon funds are insufficient.
"""

import json
import logging
import os
import subprocess
import time
from pathlib import Path
from typing import Optional

from eth_typing import ChecksumAddress
from web3 import Web3

from prediction_market_agent_tooling.config import APIKeys
from prediction_market_agent_tooling.gtypes import Wei

logger = logging.getLogger(__name__)

# Native token addresses
XDAI_ADDRESS = Web3.to_checksum_address("0xEeeeeEeeeEeEeeEeEeEeeEEEeeeeEeeeeeeeEEeE")
WPOL_ADDRESS = Web3.to_checksum_address("0x0d500B1d8E8eF31E21C99d1Db9A6444d3ADf1270")  # Wrapped POL on Polygon
USDCE_ADDRESS = Web3.to_checksum_address("0x2791Bca1f2de4661ED88A30C99A7a9449Aa84174")  # USDC.e on Polygon

# Bridge service path
BRIDGE_SERVICE_PATH = Path(__file__).parent.parent.parent.parent / "services" / "cow-bridge" / "dist" / "bridge.js"

# Bridge configuration
BRIDGE_TIMEOUT_SECONDS = int(os.getenv("BRIDGE_TIMEOUT_SECONDS", "180"))  # 3 minutes
BRIDGE_MIN_AMOUNT_USD = float(os.getenv("BRIDGE_MIN_AMOUNT_USD", "1.0"))  # $1 minimum
ENABLE_CROSS_CHAIN_BRIDGE = os.getenv("ENABLE_CROSS_CHAIN_BRIDGE", "true").lower() == "true"


class BridgeError(Exception):
    """Raised when bridge operation fails."""
    pass


def bridge_from_gnosis_to_polygon(
    amount_wei: Wei,
    buy_token: ChecksumAddress,
    api_keys: APIKeys,
    timeout: int = BRIDGE_TIMEOUT_SECONDS,
) -> str:
    """
    Bridge xDAI from Gnosis to buy_token on Polygon using CoW Protocol.
    
    Args:
        amount_wei: Amount of xDAI to bridge (in wei)
        buy_token: Destination token address on Polygon (USDC.e or WPOL)
        api_keys: API keys containing private key for signing
        timeout: Maximum seconds to wait for bridge completion
    
    Returns:
        Destination chain transaction hash
    
    Raises:
        BridgeError: If bridge fails or times out
        ValueError: If inputs are invalid
    """
    if not ENABLE_CROSS_CHAIN_BRIDGE:
        raise BridgeError("Cross-chain bridge is disabled. Set ENABLE_CROSS_CHAIN_BRIDGE=true to enable.")
    
    if not BRIDGE_SERVICE_PATH.exists():
        raise BridgeError(
            f"Bridge service not found at {BRIDGE_SERVICE_PATH}. "
            "Run 'cd services/cow-bridge && npm install && npm run build' to set up the service."
        )
    
    # Validate buy token
    if buy_token not in [USDCE_ADDRESS, WPOL_ADDRESS]:
        raise ValueError(f"Unsupported buy token: {buy_token}. Only USDC.e and WPOL are supported.")
    
    # Check minimum amount
    amount_usd = float(amount_wei.as_token)  # Assuming 1:1 xDAI:USD
    if amount_usd < BRIDGE_MIN_AMOUNT_USD:
        raise ValueError(
            f"Bridge amount ${amount_usd:.2f} is below minimum ${BRIDGE_MIN_AMOUNT_USD}. "
            "Small bridges are uneconomical due to gas costs."
        )
    
    logger.info(
        f"Initiating cross-chain bridge: {amount_wei.as_token} xDAI → {buy_token} on Polygon"
    )
    
    try:
        # Call Node.js bridge service
        result = subprocess.run(
            [
                "node",
                str(BRIDGE_SERVICE_PATH),
                "--sellToken", XDAI_ADDRESS,
                "--buyToken", buy_token,
                "--amount", str(amount_wei.value),
                "--privateKey", api_keys.bet_from_private_key.get_secret_value(),
            ],
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        
        # Parse JSON response
        try:
            response = json.loads(result.stdout)
        except json.JSONDecodeError as e:
            raise BridgeError(
                f"Failed to parse bridge service response. "
                f"stdout: {result.stdout[:500]}, stderr: {result.stderr[:500]}"
            ) from e
        
        if not response.get("success"):
            error_msg = response.get("error", "Unknown error")
            raise BridgeError(f"Bridge failed: {error_msg}")
        
        tx_hash = response.get("txHash")
        if not tx_hash:
            raise BridgeError("Bridge succeeded but no transaction hash returned")
        
        estimated_time = response.get("estimatedTime", 120)
        logger.info(
            f"Bridge order submitted successfully. "
            f"Estimated settlement time: {estimated_time}s. "
            f"Destination tx: {tx_hash}"
        )
        
        return tx_hash
        
    except subprocess.TimeoutExpired as e:
        raise BridgeError(
            f"Bridge timed out after {timeout}s. "
            "The order may still be processing. Check your wallet on Polygon."
        ) from e
    except FileNotFoundError as e:
        raise BridgeError(
            "Node.js not found. Install Node.js to use cross-chain bridge."
        ) from e


def check_gnosis_balance_and_bridge_if_needed(
    polygon_token: ChecksumAddress,
    required_amount_wei: Wei,
    api_keys: APIKeys,
) -> bool:
    """
    Check if we have enough xDAI on Gnosis to bridge to Polygon.
    If yes, initiate bridge. If no, return False.
    
    Args:
        polygon_token: Destination token address on Polygon (USDC.e or WPOL)
        required_amount_wei: Amount needed on Polygon (in destination token wei)
        api_keys: API keys for wallet access
    
    Returns:
        True if bridge was initiated successfully, False if insufficient funds
    
    Raises:
        BridgeError: If bridge fails
    """
    if not ENABLE_CROSS_CHAIN_BRIDGE:
        logger.debug("Cross-chain bridge is disabled")
        return False
    
    # Get xDAI balance on Gnosis
    gnosis_web3 = Web3(Web3.HTTPProvider("https://rpc.gnosischain.com"))
    xdai_balance_wei = gnosis_web3.eth.get_balance(api_keys.bet_from_address)
    
    logger.info(
        f"Gnosis xDAI balance: {Wei(xdai_balance_wei).as_token} xDAI. "
        f"Required on Polygon: {required_amount_wei.as_token} tokens."
    )
    
    # Estimate how much xDAI we need to bridge
    # Assuming 1:1 xDAI:USDC and similar for POL (rough estimate)
    # In production, this should query CoW API for exact quote
    estimated_xdai_needed = required_amount_wei
    
    # Add 5% buffer for slippage and fees
    xdai_to_bridge = Wei(int(estimated_xdai_needed.value * 1.05))
    
    if xdai_balance_wei < xdai_to_bridge.value:
        logger.warning(
            f"Insufficient xDAI on Gnosis. "
            f"Have: {Wei(xdai_balance_wei).as_token}, "
            f"Need: {xdai_to_bridge.as_token}"
        )
        return False
    
    # Initiate bridge
    try:
        tx_hash = bridge_from_gnosis_to_polygon(
            amount_wei=xdai_to_bridge,
            buy_token=polygon_token,
            api_keys=api_keys,
        )
        logger.info(f"Bridge initiated successfully: {tx_hash}")
        return True
    except BridgeError as e:
        logger.error(f"Bridge failed: {e}")
        raise


def get_bridge_status(tx_hash: str) -> dict:
    """
    Check the status of a bridge transaction.
    
    Args:
        tx_hash: Destination chain transaction hash
    
    Returns:
        Status dict with 'confirmed', 'block_number', etc.
    
    Note: This is a placeholder. Actual implementation would query Polygon RPC.
    """
    polygon_web3 = Web3(Web3.HTTPProvider("https://polygon-rpc.com"))
    
    try:
        receipt = polygon_web3.eth.get_transaction_receipt(tx_hash)
        return {
            "confirmed": receipt["status"] == 1,
            "block_number": receipt["blockNumber"],
            "gas_used": receipt["gasUsed"],
        }
    except Exception as e:
        return {
            "confirmed": False,
            "error": str(e),
        }
