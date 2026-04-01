from unittest.mock import MagicMock, patch

from prediction_market_agent_tooling.markets.polymarket.api import (
    get_last_trade_price_from_clob,
)


def _mock_response(json_data: dict, status_code: int = 200) -> MagicMock:
    resp = MagicMock()
    resp.status_code = status_code
    resp.json.return_value = json_data
    resp.raise_for_status.return_value = None
    return resp


@patch("prediction_market_agent_tooling.markets.polymarket.api.HttpxCachedClient")
def test_returns_price_as_float(mock_client_cls: MagicMock) -> None:
    mock_client = mock_client_cls.return_value.get_client.return_value
    mock_client.get.return_value = _mock_response({"price": "0.73"})

    result = get_last_trade_price_from_clob(token_id=12345)

    assert result == 0.73
    mock_client.get.assert_called_once()


@patch("prediction_market_agent_tooling.markets.polymarket.api.HttpxCachedClient")
def test_returns_none_when_price_is_null(mock_client_cls: MagicMock) -> None:
    mock_client = mock_client_cls.return_value.get_client.return_value
    mock_client.get.return_value = _mock_response({"price": None})

    result = get_last_trade_price_from_clob(token_id=99999)

    assert result is None


@patch("prediction_market_agent_tooling.markets.polymarket.api.HttpxCachedClient")
def test_returns_none_when_price_is_empty_string(mock_client_cls: MagicMock) -> None:
    mock_client = mock_client_cls.return_value.get_client.return_value
    mock_client.get.return_value = _mock_response({"price": ""})

    result = get_last_trade_price_from_clob(token_id=99999)

    assert result is None
