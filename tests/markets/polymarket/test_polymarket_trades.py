from unittest.mock import MagicMock, patch

from web3 import Web3

from prediction_market_agent_tooling.gtypes import (
    ChecksumAddress,
    CollateralToken,
    OutcomeStr,
)
from prediction_market_agent_tooling.markets.polymarket.api import (
    get_trades_for_market,
    get_user_trades,
)
from prediction_market_agent_tooling.markets.polymarket.data_models import (
    PolymarketSideEnum,
    PolymarketTradeResponse,
)
from prediction_market_agent_tooling.tools.hexbytes_custom import HexBytes
from prediction_market_agent_tooling.tools.utils import DatetimeUTC

MOCK_USER: ChecksumAddress = Web3.to_checksum_address(
    "0x775634755e33a2e196172d4f8fc1276b241dc666"
)
MOCK_CONDITION_ID = HexBytes(
    "0x9deb0baac40648821f96f01339229a422e2f5c877de55dc4dbf981f95a1e709c"  # web3-private-key-ok
)


def _make_trade_dict(**overrides: object) -> dict[str, object]:
    defaults: dict[str, object] = {
        "proxyWallet": "0x775634755e33a2e196172d4f8fc1276b241dc666",
        "side": "BUY",
        "asset": "12345",
        "conditionId": "0x9deb0baac40648821f96f01339229a422e2f5c877de55dc4dbf981f95a1e709c",  # web3-private-key-ok
        "size": 100.0,
        "price": 0.6,
        "timestamp": 1700000000,
        "title": "Will it rain tomorrow?",
        "slug": "will-it-rain-tomorrow",
        "icon": "https://example.com/icon.png",
        "eventSlug": "rain-tomorrow",
        "outcome": "Yes",
        "outcomeIndex": 0,
        "name": "testuser",
        "pseudonym": "Test-User",
        "bio": "",
        "profileImage": "",
        "profileImageOptimized": "",
        "transactionHash": "0xabc123",
    }
    defaults.update(overrides)
    return defaults


class TestPolymarketTradeResponse:
    def test_model_validation(self) -> None:
        trade = PolymarketTradeResponse.model_validate(_make_trade_dict())
        assert trade.side == PolymarketSideEnum.BUY
        assert trade.size == 100.0
        assert trade.price == 0.6
        assert trade.outcome == OutcomeStr("Yes")
        assert trade.transactionHash == HexBytes("0xabc123")

    def test_cost_property(self) -> None:
        trade = PolymarketTradeResponse.model_validate(
            _make_trade_dict(size=50.0, price=0.8)
        )
        assert trade.cost == CollateralToken(40.0)

    def test_to_polymarket_bet(self) -> None:
        trade = PolymarketTradeResponse.model_validate(_make_trade_dict())
        bet = trade.to_polymarket_bet()

        assert bet.id == trade.transactionHash.to_0x_hex()
        assert bet.market == trade.conditionId
        assert bet.asset_id == trade.asset
        assert bet.side == PolymarketSideEnum.BUY
        assert bet.size == 100.0
        assert bet.price == 0.6
        assert bet.match_time == trade.timestamp
        assert bet.outcome == OutcomeStr("Yes")
        assert bet.event_slug == "rain-tomorrow"
        assert bet.title == "Will it rain tomorrow?"


def _mock_response(data: list[dict[str, object]]) -> MagicMock:
    mock = MagicMock()
    mock.json.return_value = data
    mock.raise_for_status.return_value = None
    return mock


class TestGetUserTrades:
    @patch("prediction_market_agent_tooling.markets.polymarket.api.Client")
    def test_single_page(self, mock_client_cls: MagicMock) -> None:
        trades = [_make_trade_dict(transactionHash=f"0x{i}") for i in range(3)]
        mock_client = mock_client_cls.return_value
        mock_client.get.return_value = _mock_response(trades)

        result = get_user_trades(user_address=MOCK_USER)

        assert len(result) == 3
        mock_client.get.assert_called_once()

    @patch("prediction_market_agent_tooling.markets.polymarket.api.Client")
    def test_multi_page_pagination(self, mock_client_cls: MagicMock) -> None:
        page1 = [_make_trade_dict(transactionHash=f"0x{i}") for i in range(100)]
        page2 = [_make_trade_dict(transactionHash=f"0x{i}") for i in range(100, 150)]
        mock_client = mock_client_cls.return_value
        mock_client.get.side_effect = [_mock_response(page1), _mock_response(page2)]

        result = get_user_trades(user_address=MOCK_USER)

        assert len(result) == 150
        assert mock_client.get.call_count == 2

    @patch("prediction_market_agent_tooling.markets.polymarket.api.HttpxCachedClient")
    def test_limit_respected(self, mock_client_cls: MagicMock) -> None:
        page = [_make_trade_dict(transactionHash=f"0x{i}") for i in range(100)]
        mock_client = mock_client_cls.return_value.get_client.return_value
        mock_client.get.return_value = _mock_response(page)

        result = get_user_trades(user_address=MOCK_USER, limit=50)

        assert len(result) == 50

    @patch("prediction_market_agent_tooling.markets.polymarket.api.Client")
    def test_time_filtering_after(self, mock_client_cls: MagicMock) -> None:
        trades = [
            _make_trade_dict(timestamp=1700000100, transactionHash="0xa"),
            _make_trade_dict(timestamp=1700000050, transactionHash="0xb"),
            _make_trade_dict(timestamp=1700000000, transactionHash="0xc"),
        ]
        mock_client = mock_client_cls.return_value
        mock_client.get.return_value = _mock_response(trades)

        after = DatetimeUTC.to_datetime_utc(1700000060)
        result = get_user_trades(user_address=MOCK_USER, after=after)

        assert len(result) == 1
        assert result[0].transactionHash == HexBytes("0xa")

    @patch("prediction_market_agent_tooling.markets.polymarket.api.Client")
    def test_time_filtering_before(self, mock_client_cls: MagicMock) -> None:
        trades = [
            _make_trade_dict(timestamp=1700000100, transactionHash="0xa"),
            _make_trade_dict(timestamp=1700000050, transactionHash="0xb"),
            _make_trade_dict(timestamp=1700000000, transactionHash="0xc"),
        ]
        mock_client = mock_client_cls.return_value
        mock_client.get.return_value = _mock_response(trades)

        before = DatetimeUTC.to_datetime_utc(1700000060)
        result = get_user_trades(user_address=MOCK_USER, before=before)

        assert len(result) == 2
        assert result[0].transactionHash == HexBytes("0xb")
        assert result[1].transactionHash == HexBytes("0xc")

    @patch("prediction_market_agent_tooling.markets.polymarket.api.Client")
    def test_time_filtering_combined(self, mock_client_cls: MagicMock) -> None:
        trades = [
            _make_trade_dict(timestamp=1700000100, transactionHash="0xa"),
            _make_trade_dict(timestamp=1700000050, transactionHash="0xb"),
            _make_trade_dict(timestamp=1700000000, transactionHash="0xc"),
        ]
        mock_client = mock_client_cls.return_value
        mock_client.get.return_value = _mock_response(trades)

        after = DatetimeUTC.to_datetime_utc(1700000010)
        before = DatetimeUTC.to_datetime_utc(1700000060)
        result = get_user_trades(user_address=MOCK_USER, after=after, before=before)

        assert len(result) == 1
        assert result[0].transactionHash == HexBytes("0xb")

    @patch("prediction_market_agent_tooling.markets.polymarket.api.Client")
    def test_empty_response(self, mock_client_cls: MagicMock) -> None:
        mock_client = mock_client_cls.return_value
        mock_client.get.return_value = _mock_response([])

        result = get_user_trades(user_address=MOCK_USER)

        assert result == []


class TestGetTradesForMarket:
    @patch("prediction_market_agent_tooling.markets.polymarket.api.Client")
    def test_market_filter(self, mock_client_cls: MagicMock) -> None:
        trades = [_make_trade_dict()]
        mock_client = mock_client_cls.return_value
        mock_client.get.return_value = _mock_response(trades)

        result = get_trades_for_market(market=MOCK_CONDITION_ID)

        assert len(result) == 1
        call_params = mock_client.get.call_args[1]["params"]
        assert call_params["market"] == MOCK_CONDITION_ID.to_0x_hex()

    @patch("prediction_market_agent_tooling.markets.polymarket.api.Client")
    def test_market_with_user_filter(self, mock_client_cls: MagicMock) -> None:
        trades = [_make_trade_dict()]
        mock_client = mock_client_cls.return_value
        mock_client.get.return_value = _mock_response(trades)

        result = get_trades_for_market(market=MOCK_CONDITION_ID, user=MOCK_USER)

        assert len(result) == 1
        call_params = mock_client.get.call_args[1]["params"]
        assert call_params["user"] == MOCK_USER

    @patch("prediction_market_agent_tooling.markets.polymarket.api.Client")
    def test_market_without_user_omits_param(self, mock_client_cls: MagicMock) -> None:
        mock_client = mock_client_cls.return_value
        mock_client.get.return_value = _mock_response([])

        get_trades_for_market(market=MOCK_CONDITION_ID)

        call_params = mock_client.get.call_args[1]["params"]
        assert "user" not in call_params
