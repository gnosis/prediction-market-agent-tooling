from unittest.mock import MagicMock, patch

import pytest

from prediction_market_agent_tooling.gtypes import USD, CollateralToken, OutcomeStr, Wei
from prediction_market_agent_tooling.markets.polymarket.polymarket import (
    PolymarketAgentMarket,
)


def test_get_outcome_str_from_bool_true() -> None:
    assert PolymarketAgentMarket.get_outcome_str_from_bool(True) == OutcomeStr("Yes")


def test_get_outcome_str_from_bool_false() -> None:
    assert PolymarketAgentMarket.get_outcome_str_from_bool(False) == OutcomeStr("No")


@patch("prediction_market_agent_tooling.markets.polymarket.polymarket.get_usd_in_token")
def test_get_usd_in_token(
    mock_get_usd: MagicMock,
    mock_polymarket_market: PolymarketAgentMarket,
) -> None:
    mock_get_usd.return_value = CollateralToken(100.0)
    result = mock_polymarket_market.get_usd_in_token(USD(100))
    assert result == CollateralToken(100.0)
    mock_get_usd.assert_called_once_with(
        USD(100), PolymarketAgentMarket.collateral_token_address()
    )


@patch("prediction_market_agent_tooling.markets.polymarket.polymarket.get_usd_in_token")
def test_get_usd_in_token_zero(
    mock_get_usd: MagicMock,
    mock_polymarket_market: PolymarketAgentMarket,
) -> None:
    mock_get_usd.return_value = CollateralToken(0.0)
    result = mock_polymarket_market.get_usd_in_token(USD(0))
    assert result == CollateralToken(0.0)


@patch("prediction_market_agent_tooling.markets.polymarket.polymarket.USDCeContract")
def test_get_user_balance(mock_usdc_cls: MagicMock) -> None:
    mock_usdc = mock_usdc_cls.return_value
    mock_usdc.balanceOf.return_value = Wei(5_000_000)

    balance = PolymarketAgentMarket.get_user_balance(
        "0x0000000000000000000000000000000000000001"
    )

    assert balance == pytest.approx(5.0)


@patch("prediction_market_agent_tooling.markets.polymarket.polymarket.USDCeContract")
def test_get_user_balance_zero(mock_usdc_cls: MagicMock) -> None:
    mock_usdc = mock_usdc_cls.return_value
    mock_usdc.balanceOf.return_value = Wei(0)

    balance = PolymarketAgentMarket.get_user_balance(
        "0x0000000000000000000000000000000000000001"
    )

    assert balance == 0.0
