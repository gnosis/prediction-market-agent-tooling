from unittest.mock import MagicMock, patch

import pytest

from prediction_market_agent_tooling.gtypes import (
    USD,
    CollateralToken,
    OutcomeStr,
    OutcomeToken,
)
from prediction_market_agent_tooling.markets.polymarket.data_models import (
    PolymarketSideEnum,
)
from prediction_market_agent_tooling.markets.polymarket.polymarket import (
    PolymarketAgentMarket,
)


@patch("prediction_market_agent_tooling.markets.polymarket.polymarket.ClobManager")
def test_valid_calculation(
    mock_clob_cls: MagicMock,
    mock_polymarket_market: PolymarketAgentMarket,
) -> None:
    mock_clob_cls.return_value.get_token_price.return_value = USD(0.4)

    result = mock_polymarket_market.get_buy_token_amount(
        bet_amount=USD(10), outcome_str=OutcomeStr("Yes")
    )

    assert result == OutcomeToken(25.0)
    mock_clob_cls.return_value.get_token_price.assert_called_once_with(
        token_id=111, side=PolymarketSideEnum.BUY
    )


def test_invalid_outcome_raises(
    mock_polymarket_market: PolymarketAgentMarket,
) -> None:
    with pytest.raises(ValueError, match="not found in market outcomes"):
        mock_polymarket_market.get_buy_token_amount(
            bet_amount=USD(10), outcome_str=OutcomeStr("Maybe")
        )


@patch("prediction_market_agent_tooling.markets.polymarket.polymarket.ClobManager")
def test_zero_price_raises(
    mock_clob_cls: MagicMock,
    mock_polymarket_market: PolymarketAgentMarket,
) -> None:
    mock_clob_cls.return_value.get_token_price.return_value = USD(0)

    with pytest.raises(ValueError, match="Could not get price"):
        mock_polymarket_market.get_buy_token_amount(
            bet_amount=USD(10), outcome_str=OutcomeStr("Yes")
        )


@patch("prediction_market_agent_tooling.markets.polymarket.polymarket.ClobManager")
def test_with_collateral_token_input(
    mock_clob_cls: MagicMock,
    mock_polymarket_market: PolymarketAgentMarket,
) -> None:
    mock_clob_cls.return_value.get_token_price.return_value = USD(0.5)

    result = mock_polymarket_market.get_buy_token_amount(
        bet_amount=CollateralToken(5), outcome_str=OutcomeStr("Yes")
    )

    assert result == OutcomeToken(10.0)
