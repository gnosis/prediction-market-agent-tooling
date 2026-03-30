from unittest.mock import MagicMock, patch

import pytest

from prediction_market_agent_tooling.gtypes import USD, OutcomeStr, OutcomeToken, Wei
from prediction_market_agent_tooling.markets.polymarket.clob_manager import (
    CreateOrderResult,
    OrderStatusEnum,
    PolymarketPriceSideEnum,
)
from prediction_market_agent_tooling.markets.polymarket.polymarket import (
    PolymarketAgentMarket,
)
from prediction_market_agent_tooling.tools.hexbytes_custom import HexBytes

MOCK_TX_HASH = HexBytes(
    "0xabc123def456abc123def456abc123def456abc123def456abc123def456abc1"  # web3-private-key-ok
)


def _success_order_result() -> CreateOrderResult:
    return CreateOrderResult(
        errorMsg="",
        orderID="order-1",
        transactionsHashes=[MOCK_TX_HASH],
        status=OrderStatusEnum.MATCHED,
        success=True,
    )


def _failed_order_result() -> CreateOrderResult:
    return CreateOrderResult(
        errorMsg="Something went wrong",
        orderID="order-2",
        transactionsHashes=[],
        status=OrderStatusEnum.UNMATCHED,
        success=False,
    )


@patch("prediction_market_agent_tooling.markets.polymarket.polymarket.ClobManager")
def test_place_bet_success(
    mock_clob_cls: MagicMock,
    mock_polymarket_market: PolymarketAgentMarket,
) -> None:
    mock_clob = mock_clob_cls.return_value
    mock_clob.place_buy_market_order.return_value = _success_order_result()

    tx_hash = mock_polymarket_market.place_bet(
        outcome=OutcomeStr("Yes"), amount=USD(10), auto_deposit=False
    )

    assert tx_hash == MOCK_TX_HASH.to_0x_hex()
    mock_clob.place_buy_market_order.assert_called_once_with(
        token_id=111, usdc_amount=USD(10)
    )


@patch("prediction_market_agent_tooling.markets.polymarket.polymarket.ClobManager")
def test_place_bet_failure_raises(
    mock_clob_cls: MagicMock,
    mock_polymarket_market: PolymarketAgentMarket,
) -> None:
    mock_clob = mock_clob_cls.return_value
    mock_clob.place_buy_market_order.return_value = _failed_order_result()

    with pytest.raises(ValueError, match="Error creating order"):
        mock_polymarket_market.place_bet(
            outcome=OutcomeStr("Yes"), amount=USD(10), auto_deposit=False
        )


@patch("prediction_market_agent_tooling.markets.polymarket.polymarket.USDCeContract")
@patch("prediction_market_agent_tooling.markets.polymarket.polymarket.ClobManager")
def test_buy_tokens_delegates_to_place_bet(
    mock_clob_cls: MagicMock,
    mock_usdce_cls: MagicMock,
    mock_polymarket_market: PolymarketAgentMarket,
) -> None:
    # Pretend wallet has enough USDC.e so auto_deposit skips the swap.
    mock_usdce_cls.return_value.balanceOf.return_value = Wei(100_000_000)
    mock_clob = mock_clob_cls.return_value
    mock_clob.place_buy_market_order.return_value = _success_order_result()

    tx_hash = mock_polymarket_market.buy_tokens(
        outcome=OutcomeStr("Yes"), amount=USD(10)
    )

    assert tx_hash == MOCK_TX_HASH.to_0x_hex()
    mock_clob.place_buy_market_order.assert_called_once_with(
        token_id=111, usdc_amount=USD(10)
    )


@patch("prediction_market_agent_tooling.markets.polymarket.polymarket.ClobManager")
def test_sell_tokens_with_outcome_token(
    mock_clob_cls: MagicMock,
    mock_polymarket_market: PolymarketAgentMarket,
) -> None:
    mock_clob = mock_clob_cls.return_value
    mock_clob.place_sell_market_order.return_value = _success_order_result()

    tx_hash = mock_polymarket_market.sell_tokens(
        outcome=OutcomeStr("No"), amount=OutcomeToken(5.0)
    )

    assert tx_hash == MOCK_TX_HASH.to_0x_hex()
    mock_clob.place_sell_market_order.assert_called_once_with(
        token_id=222, token_shares=OutcomeToken(5.0)
    )


@patch("prediction_market_agent_tooling.markets.polymarket.polymarket.ClobManager")
def test_sell_tokens_with_usd(
    mock_clob_cls: MagicMock,
    mock_polymarket_market: PolymarketAgentMarket,
) -> None:
    mock_clob = mock_clob_cls.return_value
    mock_clob.get_token_price.return_value = USD(0.5)
    mock_clob.place_sell_market_order.return_value = _success_order_result()

    tx_hash = mock_polymarket_market.sell_tokens(
        outcome=OutcomeStr("Yes"), amount=USD(10)
    )

    assert tx_hash == MOCK_TX_HASH.to_0x_hex()
    mock_clob.get_token_price.assert_called_once_with(
        token_id=111, side=PolymarketPriceSideEnum.SELL
    )
    mock_clob.place_sell_market_order.assert_called_once_with(
        token_id=111, token_shares=OutcomeToken(20.0)
    )
