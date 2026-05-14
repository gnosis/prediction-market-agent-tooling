"""
Unit tests for cross-chain bridge functionality.
"""

import json
import subprocess
from unittest.mock import MagicMock, patch

import pytest
from eth_typing import ChecksumAddress
from web3 import Web3

from prediction_market_agent_tooling.config import APIKeys
from prediction_market_agent_tooling.gtypes import Wei
from prediction_market_agent_tooling.tools.tokens.cross_chain_bridge import (
    USDCE_ADDRESS,
    WPOL_ADDRESS,
    XDAI_ADDRESS,
    BridgeError,
    bridge_from_gnosis_to_polygon,
    check_gnosis_balance_and_bridge_if_needed,
)


@pytest.fixture
def mock_api_keys():
    """Mock API keys for testing."""
    keys = MagicMock(spec=APIKeys)
    keys.bet_from_address = Web3.to_checksum_address("0x1234567890123456789012345678901234567890")
    keys.bet_from_private_key = MagicMock()
    keys.bet_from_private_key.get_secret_value.return_value = "0xabcd1234"
    return keys


class TestBridgeFromGnosisToPolygon:
    """Tests for bridge_from_gnosis_to_polygon function."""
    
    @patch("prediction_market_agent_tooling.tools.tokens.cross_chain_bridge.ENABLE_CROSS_CHAIN_BRIDGE", True)
    @patch("prediction_market_agent_tooling.tools.tokens.cross_chain_bridge.BRIDGE_SERVICE_PATH")
    @patch("subprocess.run")
    def test_successful_bridge(self, mock_run, mock_path, mock_api_keys):
        """Test successful bridge operation."""
        mock_path.exists.return_value = True
        
        # Mock successful bridge response
        mock_run.return_value = MagicMock(
            stdout=json.dumps({
                "success": True,
                "txHash": "0xabcd1234",
                "estimatedTime": 120
            }),
            returncode=0
        )
        
        tx_hash = bridge_from_gnosis_to_polygon(
            amount_wei=Wei(int(1e18)),  # 1 xDAI
            buy_token=USDCE_ADDRESS,
            api_keys=mock_api_keys,
        )
        
        assert tx_hash == "0xabcd1234"
        mock_run.assert_called_once()
    
    @patch("prediction_market_agent_tooling.tools.tokens.cross_chain_bridge.ENABLE_CROSS_CHAIN_BRIDGE", False)
    def test_bridge_disabled(self, mock_api_keys):
        """Test that bridge raises error when disabled."""
        with pytest.raises(BridgeError, match="disabled"):
            bridge_from_gnosis_to_polygon(
                amount_wei=Wei(int(1e18)),
                buy_token=USDCE_ADDRESS,
                api_keys=mock_api_keys,
            )
    
    @patch("prediction_market_agent_tooling.tools.tokens.cross_chain_bridge.ENABLE_CROSS_CHAIN_BRIDGE", True)
    @patch("prediction_market_agent_tooling.tools.tokens.cross_chain_bridge.BRIDGE_SERVICE_PATH")
    def test_service_not_found(self, mock_path, mock_api_keys):
        """Test error when bridge service is not built."""
        mock_path.exists.return_value = False
        
        with pytest.raises(BridgeError, match="not found"):
            bridge_from_gnosis_to_polygon(
                amount_wei=Wei(int(1e18)),
                buy_token=USDCE_ADDRESS,
                api_keys=mock_api_keys,
            )
    
    @patch("prediction_market_agent_tooling.tools.tokens.cross_chain_bridge.ENABLE_CROSS_CHAIN_BRIDGE", True)
    @patch("prediction_market_agent_tooling.tools.tokens.cross_chain_bridge.BRIDGE_SERVICE_PATH")
    def test_invalid_buy_token(self, mock_path, mock_api_keys):
        """Test error with unsupported buy token."""
        mock_path.exists.return_value = True
        
        invalid_token = Web3.to_checksum_address("0x0000000000000000000000000000000000000000")
        
        with pytest.raises(ValueError, match="Unsupported buy token"):
            bridge_from_gnosis_to_polygon(
                amount_wei=Wei(int(1e18)),
                buy_token=invalid_token,
                api_keys=mock_api_keys,
            )
    
    @patch("prediction_market_agent_tooling.tools.tokens.cross_chain_bridge.ENABLE_CROSS_CHAIN_BRIDGE", True)
    @patch("prediction_market_agent_tooling.tools.tokens.cross_chain_bridge.BRIDGE_SERVICE_PATH")
    @patch("prediction_market_agent_tooling.tools.tokens.cross_chain_bridge.BRIDGE_MIN_AMOUNT_USD", 1.0)
    def test_amount_below_minimum(self, mock_path, mock_api_keys):
        """Test error when amount is below minimum."""
        mock_path.exists.return_value = True
        
        with pytest.raises(ValueError, match="below minimum"):
            bridge_from_gnosis_to_polygon(
                amount_wei=Wei(int(0.5e18)),  # $0.50
                buy_token=USDCE_ADDRESS,
                api_keys=mock_api_keys,
            )
    
    @patch("prediction_market_agent_tooling.tools.tokens.cross_chain_bridge.ENABLE_CROSS_CHAIN_BRIDGE", True)
    @patch("prediction_market_agent_tooling.tools.tokens.cross_chain_bridge.BRIDGE_SERVICE_PATH")
    @patch("subprocess.run")
    def test_bridge_failure(self, mock_run, mock_path, mock_api_keys):
        """Test handling of bridge failure."""
        mock_path.exists.return_value = True
        
        # Mock failed bridge response
        mock_run.return_value = MagicMock(
            stdout=json.dumps({
                "success": False,
                "error": "Insufficient liquidity"
            }),
            returncode=1
        )
        
        with pytest.raises(BridgeError, match="Insufficient liquidity"):
            bridge_from_gnosis_to_polygon(
                amount_wei=Wei(int(1e18)),
                buy_token=USDCE_ADDRESS,
                api_keys=mock_api_keys,
            )
    
    @patch("prediction_market_agent_tooling.tools.tokens.cross_chain_bridge.ENABLE_CROSS_CHAIN_BRIDGE", True)
    @patch("prediction_market_agent_tooling.tools.tokens.cross_chain_bridge.BRIDGE_SERVICE_PATH")
    @patch("subprocess.run")
    def test_timeout(self, mock_run, mock_path, mock_api_keys):
        """Test handling of bridge timeout."""
        mock_path.exists.return_value = True
        mock_run.side_effect = subprocess.TimeoutExpired("node", 180)
        
        with pytest.raises(BridgeError, match="timed out"):
            bridge_from_gnosis_to_polygon(
                amount_wei=Wei(int(1e18)),
                buy_token=USDCE_ADDRESS,
                api_keys=mock_api_keys,
                timeout=180,
            )


class TestCheckGnosisBalanceAndBridge:
    """Tests for check_gnosis_balance_and_bridge_if_needed function."""
    
    @patch("prediction_market_agent_tooling.tools.tokens.cross_chain_bridge.ENABLE_CROSS_CHAIN_BRIDGE", True)
    @patch("prediction_market_agent_tooling.tools.tokens.cross_chain_bridge.Web3")
    @patch("prediction_market_agent_tooling.tools.tokens.cross_chain_bridge.bridge_from_gnosis_to_polygon")
    def test_sufficient_balance_bridges(self, mock_bridge, mock_web3_class, mock_api_keys):
        """Test that bridge is initiated when sufficient xDAI balance."""
        # Mock Gnosis balance check
        mock_web3 = MagicMock()
        mock_web3.eth.get_balance.return_value = int(2e18)  # 2 xDAI
        mock_web3_class.return_value = mock_web3
        
        # Mock successful bridge
        mock_bridge.return_value = "0xtxhash"
        
        result = check_gnosis_balance_and_bridge_if_needed(
            polygon_token=USDCE_ADDRESS,
            required_amount_wei=Wei(int(1e18)),  # Need 1 token
            api_keys=mock_api_keys,
        )
        
        assert result is True
        mock_bridge.assert_called_once()
    
    @patch("prediction_market_agent_tooling.tools.tokens.cross_chain_bridge.ENABLE_CROSS_CHAIN_BRIDGE", True)
    @patch("prediction_market_agent_tooling.tools.tokens.cross_chain_bridge.Web3")
    def test_insufficient_balance_returns_false(self, mock_web3_class, mock_api_keys):
        """Test that function returns False when insufficient xDAI."""
        # Mock Gnosis balance check
        mock_web3 = MagicMock()
        mock_web3.eth.get_balance.return_value = int(0.5e18)  # 0.5 xDAI
        mock_web3_class.return_value = mock_web3
        
        result = check_gnosis_balance_and_bridge_if_needed(
            polygon_token=USDCE_ADDRESS,
            required_amount_wei=Wei(int(1e18)),  # Need 1 token
            api_keys=mock_api_keys,
        )
        
        assert result is False
    
    @patch("prediction_market_agent_tooling.tools.tokens.cross_chain_bridge.ENABLE_CROSS_CHAIN_BRIDGE", False)
    def test_disabled_returns_false(self, mock_api_keys):
        """Test that function returns False when bridge is disabled."""
        result = check_gnosis_balance_and_bridge_if_needed(
            polygon_token=USDCE_ADDRESS,
            required_amount_wei=Wei(int(1e18)),
            api_keys=mock_api_keys,
        )
        
        assert result is False
