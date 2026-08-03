from unittest.mock import MagicMock, patch

import pytest
import tenacity

from prediction_market_agent_tooling.markets.polymarket.api import (
    get_gamma_event_by_id,
    get_gamma_event_by_slug,
    get_polymarkets_with_pagination,
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


@patch("prediction_market_agent_tooling.markets.polymarket.api.logger")
@patch("prediction_market_agent_tooling.markets.polymarket.api.Client")
def test_get_polymarkets_with_pagination_skips_event_without_markets(
    mock_client_cls: MagicMock, mock_logger: MagicMock
) -> None:
    # Leftover Polymarket events (e.g. id 4871) come back without the `markets` field
    # at all, they must be skipped instead of breaking the whole batch.
    event_without_markets = {
        "id": "4871",
        "slug": "will-there-be-an-emergency-use-authorization-eua-granted-for-a-covid-19-vaccine-before-2021",
        "title": "Will there be an EUA granted for a COVID-19 vaccine before 2021?",
        "startDate": "2020-11-09T00:00:00Z",
        "archived": False,
        "closed": True,
        "active": True,
    }
    event_with_markets = _mock_event_json() | {"startDate": "2025-01-01T00:00:00Z"}
    mock_response = MagicMock()
    mock_response.json.return_value = {
        "data": [event_without_markets, event_with_markets],
        "pagination": {"hasMore": False},
    }
    mock_response.raise_for_status = MagicMock()
    mock_response.headers = {"content-type": "application/json"}
    mock_client_cls.return_value.get.return_value = mock_response

    markets = get_polymarkets_with_pagination(limit=10)

    assert [m.id for m in markets] == ["12345"]
    mock_logger.info.assert_called_once()
    assert "4871" in mock_logger.info.call_args.args[0]
