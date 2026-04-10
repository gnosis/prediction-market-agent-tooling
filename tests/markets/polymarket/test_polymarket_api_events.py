from unittest.mock import MagicMock, patch

import pytest
import tenacity

from prediction_market_agent_tooling.markets.polymarket.api import (
    get_gamma_event_by_id,
    get_gamma_event_by_slug,
)
from prediction_market_agent_tooling.markets.polymarket.data_models import (
    PolymarketGammaResponseDataItem,
)


def _mock_event_json() -> dict[str, object]:
    return {
        "id": "12345",
        "slug": "test-market",
        "title": "Will it rain?",
        "description": "Test",
        "archived": False,
        "closed": False,
        "active": True,
        "markets": [
            {
                "conditionId": "0xabc123",
                "outcomes": '["Yes","No"]',
                "outcomePrices": "[0.6,0.4]",
                "marketMakerAddress": "0xDEF",
                "createdAt": "2025-01-01T00:00:00Z",
                "archived": False,
                "clobTokenIds": "[111,222]",
                "question": "Will it rain?",
            }
        ],
    }


@patch("prediction_market_agent_tooling.markets.polymarket.api.HttpxCachedClient")
def test_get_gamma_event_by_id(mock_client_cls: MagicMock) -> None:
    mock_response = MagicMock()
    mock_response.json.return_value = _mock_event_json()
    mock_response.raise_for_status = MagicMock()
    mock_response.headers = {"content-type": "application/json"}
    mock_client_cls.return_value.get_client.return_value.get.return_value = (
        mock_response
    )

    result = get_gamma_event_by_id("12345")

    assert isinstance(result, PolymarketGammaResponseDataItem)
    assert result.id == "12345"
    assert result.title == "Will it rain?"


@patch("prediction_market_agent_tooling.markets.polymarket.api.HttpxCachedClient")
def test_get_gamma_event_by_slug(mock_client_cls: MagicMock) -> None:
    mock_response = MagicMock()
    mock_response.json.return_value = [_mock_event_json()]
    mock_response.raise_for_status = MagicMock()
    mock_response.headers = {"content-type": "application/json"}
    mock_client_cls.return_value.get_client.return_value.get.return_value = (
        mock_response
    )

    result = get_gamma_event_by_slug("test-market")

    assert isinstance(result, PolymarketGammaResponseDataItem)
    assert result.slug == "test-market"


@patch("prediction_market_agent_tooling.markets.polymarket.api.HttpxCachedClient")
def test_get_gamma_event_by_slug_empty_raises(mock_client_cls: MagicMock) -> None:
    mock_response = MagicMock()
    mock_response.json.return_value = []
    mock_response.raise_for_status = MagicMock()
    mock_response.headers = {"content-type": "application/json"}
    mock_client_cls.return_value.get_client.return_value.get.return_value = (
        mock_response
    )

    with pytest.raises(tenacity.RetryError):
        get_gamma_event_by_slug("nonexistent-slug")
