from unittest.mock import Mock, patch

from web3 import Web3

from prediction_market_agent_tooling.gtypes import (
    CollateralToken,
    HexAddress,
    HexStr,
    OutcomeStr,
    OutcomeToken,
)
from prediction_market_agent_tooling.markets.seer.data_models import SeerMarket
from prediction_market_agent_tooling.markets.seer.price_manager import PriceManager
from prediction_market_agent_tooling.markets.seer.seer_subgraph_handler import (
    SeerSubgraphHandler,
)
from prediction_market_agent_tooling.tools.hexbytes_custom import HexBytes


def test_probability_map_strips_whitespace() -> None:
    """Test that probability map keys are stripped of whitespace and normalized to lowercase."""
    # Create mock market with outcomes containing whitespace and mixed case
    mock_market = Mock(spec=SeerMarket)
    mock_market.outcomes = [
        OutcomeStr(" Yes "),
        OutcomeStr("NO  "),
        OutcomeStr(" InVaLiD "),
    ]
    mock_market.wrapped_tokens = [
        HexAddress(HexStr("0x1234567890123456789012345678901234567890")),
        HexAddress(HexStr("0x2345678901234567890123456789012345678901")),
        HexAddress(HexStr("0x3456789012345678901234567890123456789012")),
    ]

    # Create price manager with mock market
    price_manager = PriceManager(
        seer_market=mock_market, seer_subgraph=Mock(spec=SeerSubgraphHandler)
    )

    # Mock price data
    with patch.object(PriceManager, "get_price_for_token") as mock_get_price:
        mock_get_price.side_effect = [
            CollateralToken(0.7),
            CollateralToken(0.3),
            CollateralToken(0.0),
        ]  # Yes, No, Invalid probabilities
        probability_map = price_manager.build_probability_map()

    # Verify all keys are stripped and lowercase
    assert all(key == key.strip().lower() for key in probability_map.keys())
    assert set(probability_map.keys()) == {"yes", "no", "invalid"}
    # Type checking is handled by Pydantic model validation
    assert all(isinstance(key, str) for key in probability_map.keys())
    assert all(isinstance(val, float) for val in probability_map.values())


def test_outcome_token_pool_strips_whitespace() -> None:
    """Test that outcome token pool keys are stripped of whitespace and normalized to lowercase."""
    # Create mock market with outcomes containing whitespace and mixed case
    mock_market = Mock(spec=SeerMarket)
    mock_market.outcomes = [
        OutcomeStr(" yes "),
        OutcomeStr("no  "),
        OutcomeStr(" invalid "),
    ]  # All lowercase to match expected output
    mock_market.wrapped_tokens = [
        HexAddress(HexStr("0x1234567890123456789012345678901234567890")),
        HexAddress(HexStr("0x2345678901234567890123456789012345678901")),
        HexAddress(HexStr("0x3456789012345678901234567890123456789012")),
    ]
    mock_market.collateral_token = HexAddress(
        HexStr("0x4567890123456789012345678901234567890123")
    )
    mock_market.collateral_token_contract_address_checksummed = (
        Web3.to_checksum_address(mock_market.collateral_token)
    )
    mock_market.url = "https://example.com/market/123"

    # Create price manager with mock market
    price_manager = PriceManager(
        seer_market=mock_market, seer_subgraph=Mock(spec=SeerSubgraphHandler)
    )

    # Mock pool data
    mock_pool = Mock()
    mock_pool.token0.id = HexBytes(mock_market.wrapped_tokens[0])
    mock_pool.token1.id = HexBytes(mock_market.collateral_token)
    mock_pool.totalValueLockedToken0 = 100
    mock_pool.totalValueLockedToken1 = 200
    mock_pool.token0Price = Mock(value=0.7)
    mock_pool.token1Price = Mock(value=0.3)

    def mock_get_pool(token: HexAddress, *args: object, **kwargs: object) -> Mock:
        pool = Mock()
        pool.token0.id = HexBytes(token)
        pool.token1.id = HexBytes(mock_market.collateral_token)
        pool.totalValueLockedToken0 = 100
        pool.totalValueLockedToken1 = 200
        pool.token0Price = Mock(value=0.7)
        pool.token1Price = Mock(value=0.3)
        return pool

    with patch.object(
        SeerSubgraphHandler, "get_pool_by_token", side_effect=mock_get_pool
    ):
        (
            probability_map,
            outcome_token_pool,
        ) = price_manager.build_initial_probs_from_pool(
            model=mock_market,
            wrapped_tokens=[
                Web3.to_checksum_address(token) for token in mock_market.wrapped_tokens
            ],
        )

    # Verify all keys in outcome token pool are stripped and lowercase
    assert all(key == key.strip().lower() for key in outcome_token_pool.keys())
    assert set(outcome_token_pool.keys()) == {"yes", "no", "invalid"}
    assert all(isinstance(key, str) for key in outcome_token_pool.keys())
    assert all(isinstance(val, OutcomeToken) for val in outcome_token_pool.values())

    # Verify all keys in probability map are stripped and lowercase
    assert all(key == key.strip().lower() for key in probability_map.keys())
    assert set(probability_map.keys()) == {"yes", "no", "invalid"}
    assert all(isinstance(key, str) for key in probability_map.keys())
    assert all(isinstance(val, float) for val in probability_map.values())
