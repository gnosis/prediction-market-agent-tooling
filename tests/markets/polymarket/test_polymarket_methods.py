from datetime import timedelta
from unittest.mock import MagicMock, patch

import pytest
from web3 import Web3

from prediction_market_agent_tooling.config import APIKeys
from prediction_market_agent_tooling.gtypes import (
    USD,
    ChecksumAddress,
    CollateralToken,
    OutcomeStr,
    Probability,
    Wei,
)
from prediction_market_agent_tooling.markets.data_models import Bet, ResolvedBet
from prediction_market_agent_tooling.markets.polymarket.data_models import (
    PolymarketTradeResponse,
)
from prediction_market_agent_tooling.markets.polymarket.polymarket import (
    PolymarketAgentMarket,
)
from prediction_market_agent_tooling.markets.polymarket.polymarket_subgraph_handler import (
    ConditionSubgraphModel,
)
from prediction_market_agent_tooling.tools.hexbytes_custom import HexBytes
from prediction_market_agent_tooling.tools.utils import DatetimeUTC

MOCK_USER: ChecksumAddress = Web3.to_checksum_address(
    "0x775634755e33a2e196172d4f8fc1276b241dc666"
)
MOCK_CONDITION_ID = HexBytes(
    "0x9deb0baac40648821f96f01339229a422e2f5c877de55dc4dbf981f95a1e709c"  # web3-private-key-ok
)
SECOND_CONDITION_ID = HexBytes(
    "0xabcdef1234567890abcdef1234567890abcdef1234567890abcdef1234567890"  # web3-private-key-ok
)


def _make_trade_dict(**overrides: object) -> dict[str, object]:
    defaults: dict[str, object] = {
        "proxyWallet": "0x775634755e33a2e196172d4f8fc1276b241dc666",
        "side": "BUY",
        "asset": "12345",
        "conditionId": MOCK_CONDITION_ID.to_0x_hex(),
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


def _make_trade(**overrides: object) -> PolymarketTradeResponse:
    return PolymarketTradeResponse.model_validate(_make_trade_dict(**overrides))


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


class TestGetLastTradePYes:
    @patch(
        "prediction_market_agent_tooling.markets.polymarket.polymarket.get_last_trade_price_from_clob"
    )
    def test_returns_probability(
        self,
        mock_clob: MagicMock,
        mock_polymarket_market: PolymarketAgentMarket,
    ) -> None:
        mock_clob.return_value = 0.73
        result = mock_polymarket_market.get_last_trade_p_yes()
        assert result == Probability(0.73)
        mock_clob.assert_called_once_with(token_id=111)

    @patch(
        "prediction_market_agent_tooling.markets.polymarket.polymarket.get_last_trade_price_from_clob"
    )
    def test_returns_none_when_no_trades(
        self,
        mock_clob: MagicMock,
        mock_polymarket_market: PolymarketAgentMarket,
    ) -> None:
        mock_clob.return_value = None
        result = mock_polymarket_market.get_last_trade_p_yes()
        assert result is None


class TestGetLastTradePNo:
    @patch(
        "prediction_market_agent_tooling.markets.polymarket.polymarket.get_last_trade_price_from_clob"
    )
    def test_returns_complement(
        self,
        mock_clob: MagicMock,
        mock_polymarket_market: PolymarketAgentMarket,
    ) -> None:
        mock_clob.return_value = 0.73
        result = mock_polymarket_market.get_last_trade_p_no()
        assert result == pytest.approx(Probability(0.27))

    @patch(
        "prediction_market_agent_tooling.markets.polymarket.polymarket.get_last_trade_price_from_clob"
    )
    def test_returns_none_when_no_trades(
        self,
        mock_clob: MagicMock,
        mock_polymarket_market: PolymarketAgentMarket,
    ) -> None:
        mock_clob.return_value = None
        result = mock_polymarket_market.get_last_trade_p_no()
        assert result is None


class TestGetBetsMadeSince:
    @patch(
        "prediction_market_agent_tooling.markets.polymarket.polymarket.get_user_trades"
    )
    def test_happy_path(self, mock_get_trades: MagicMock) -> None:
        mock_get_trades.return_value = [
            _make_trade(transactionHash="0x1", timestamp=1700000000),
            _make_trade(transactionHash="0x2", timestamp=1700000100),
        ]
        start = DatetimeUTC.to_datetime_utc(1699999000)
        result = PolymarketAgentMarket.get_bets_made_since(MOCK_USER, start)

        assert len(result) == 2
        assert all(isinstance(b, Bet) for b in result)
        mock_get_trades.assert_called_once_with(user_address=MOCK_USER, after=start)

    @patch(
        "prediction_market_agent_tooling.markets.polymarket.polymarket.get_user_trades"
    )
    def test_empty(self, mock_get_trades: MagicMock) -> None:
        mock_get_trades.return_value = []
        start = DatetimeUTC.to_datetime_utc(1699999000)
        result = PolymarketAgentMarket.get_bets_made_since(MOCK_USER, start)
        assert result == []

    @patch(
        "prediction_market_agent_tooling.markets.polymarket.polymarket.get_user_trades"
    )
    def test_sorted_by_created_time(self, mock_get_trades: MagicMock) -> None:
        mock_get_trades.return_value = [
            _make_trade(transactionHash="0x2", timestamp=1700000100),
            _make_trade(transactionHash="0x1", timestamp=1700000000),
        ]
        start = DatetimeUTC.to_datetime_utc(1699999000)
        result = PolymarketAgentMarket.get_bets_made_since(MOCK_USER, start)

        assert result[0].created_time < result[1].created_time


class TestGetResolvedBetsMadeSince:
    def _mock_condition(
        self,
        condition_id: HexBytes = MOCK_CONDITION_ID,
        resolution_timestamp: int | None = 1700000500,
        payout_numerators: list[int] | None = None,
    ) -> ConditionSubgraphModel:
        return ConditionSubgraphModel(
            id=condition_id,
            payoutDenominator=1,
            payoutNumerators=payout_numerators or [1, 0],
            outcomeSlotCount=2,
            resolutionTimestamp=resolution_timestamp,
            questionId=HexBytes("0xaaa"),
        )

    @patch(
        "prediction_market_agent_tooling.markets.polymarket.polymarket.PolymarketSubgraphHandler"
    )
    @patch(
        "prediction_market_agent_tooling.markets.polymarket.polymarket.get_user_trades"
    )
    def test_happy_path(
        self, mock_get_trades: MagicMock, mock_handler_cls: MagicMock
    ) -> None:
        mock_get_trades.return_value = [
            _make_trade(transactionHash="0x1", timestamp=1700000000),
        ]
        mock_handler_cls.return_value.get_conditions.return_value = [
            self._mock_condition()
        ]

        start = DatetimeUTC.to_datetime_utc(1699999000)
        result = PolymarketAgentMarket.get_resolved_bets_made_since(
            MOCK_USER, start, None
        )

        assert len(result) == 1
        assert isinstance(result[0], ResolvedBet)
        assert result[0].market_outcome == OutcomeStr("Yes")

    @patch(
        "prediction_market_agent_tooling.markets.polymarket.polymarket.PolymarketSubgraphHandler"
    )
    @patch(
        "prediction_market_agent_tooling.markets.polymarket.polymarket.get_user_trades"
    )
    def test_skips_unresolved(
        self, mock_get_trades: MagicMock, mock_handler_cls: MagicMock
    ) -> None:
        mock_get_trades.return_value = [
            _make_trade(transactionHash="0x1"),
        ]
        mock_handler_cls.return_value.get_conditions.return_value = [
            self._mock_condition(resolution_timestamp=None)
        ]

        start = DatetimeUTC.to_datetime_utc(1699999000)
        result = PolymarketAgentMarket.get_resolved_bets_made_since(
            MOCK_USER, start, None
        )
        assert result == []

    @patch(
        "prediction_market_agent_tooling.markets.polymarket.polymarket.get_user_trades"
    )
    def test_empty_trades_no_subgraph_call(self, mock_get_trades: MagicMock) -> None:
        mock_get_trades.return_value = []
        start = DatetimeUTC.to_datetime_utc(1699999000)
        result = PolymarketAgentMarket.get_resolved_bets_made_since(
            MOCK_USER, start, None
        )
        assert result == []

    @patch(
        "prediction_market_agent_tooling.markets.polymarket.polymarket.PolymarketSubgraphHandler"
    )
    @patch(
        "prediction_market_agent_tooling.markets.polymarket.polymarket.get_user_trades"
    )
    def test_mixed_resolved_and_unresolved(
        self, mock_get_trades: MagicMock, mock_handler_cls: MagicMock
    ) -> None:
        mock_get_trades.return_value = [
            _make_trade(
                transactionHash="0x1",
                conditionId=MOCK_CONDITION_ID.to_0x_hex(),
            ),
            _make_trade(
                transactionHash="0x2",
                conditionId=SECOND_CONDITION_ID.to_0x_hex(),
            ),
        ]
        mock_handler_cls.return_value.get_conditions.return_value = [
            self._mock_condition(condition_id=MOCK_CONDITION_ID),
            self._mock_condition(
                condition_id=SECOND_CONDITION_ID, resolution_timestamp=None
            ),
        ]

        start = DatetimeUTC.to_datetime_utc(1699999000)
        result = PolymarketAgentMarket.get_resolved_bets_made_since(
            MOCK_USER, start, None
        )
        assert len(result) == 1
        assert result[0].id == HexBytes("0x1").to_0x_hex()


class TestHaveBetOnMarketSince:
    @patch(
        "prediction_market_agent_tooling.markets.polymarket.polymarket.get_trades_for_market"
    )
    def test_true_when_recent_trade(
        self,
        mock_get_trades: MagicMock,
        mock_polymarket_market: PolymarketAgentMarket,
    ) -> None:
        mock_get_trades.return_value = [
            _make_trade(timestamp=int(DatetimeUTC.now().timestamp())),
        ]
        keys = MagicMock(spec=APIKeys)
        keys.bet_from_address = MOCK_USER

        assert mock_polymarket_market.have_bet_on_market_since(keys, timedelta(hours=1))

    @patch(
        "prediction_market_agent_tooling.markets.polymarket.polymarket.get_trades_for_market"
    )
    def test_false_when_old_trades(
        self,
        mock_get_trades: MagicMock,
        mock_polymarket_market: PolymarketAgentMarket,
    ) -> None:
        mock_get_trades.return_value = [
            _make_trade(timestamp=1600000000),
        ]
        keys = MagicMock(spec=APIKeys)
        keys.bet_from_address = MOCK_USER

        assert not mock_polymarket_market.have_bet_on_market_since(
            keys, timedelta(hours=1)
        )

    @patch(
        "prediction_market_agent_tooling.markets.polymarket.polymarket.get_trades_for_market"
    )
    def test_false_when_no_trades(
        self,
        mock_get_trades: MagicMock,
        mock_polymarket_market: PolymarketAgentMarket,
    ) -> None:
        mock_get_trades.return_value = []
        keys = MagicMock(spec=APIKeys)
        keys.bet_from_address = MOCK_USER

        assert not mock_polymarket_market.have_bet_on_market_since(
            keys, timedelta(hours=1)
        )


class TestGetMostRecentTradeDatetime:
    @patch(
        "prediction_market_agent_tooling.markets.polymarket.polymarket.get_trades_for_market"
    )
    def test_returns_latest_timestamp(
        self,
        mock_get_trades: MagicMock,
        mock_polymarket_market: PolymarketAgentMarket,
    ) -> None:
        mock_get_trades.return_value = [
            _make_trade(timestamp=1700000000, transactionHash="0x1"),
            _make_trade(timestamp=1700000200, transactionHash="0x2"),
            _make_trade(timestamp=1700000100, transactionHash="0x3"),
        ]

        result = mock_polymarket_market.get_most_recent_trade_datetime(str(MOCK_USER))
        assert result == DatetimeUTC.to_datetime_utc(1700000200)

    @patch(
        "prediction_market_agent_tooling.markets.polymarket.polymarket.get_trades_for_market"
    )
    def test_returns_none_when_empty(
        self,
        mock_get_trades: MagicMock,
        mock_polymarket_market: PolymarketAgentMarket,
    ) -> None:
        mock_get_trades.return_value = []
        result = mock_polymarket_market.get_most_recent_trade_datetime(str(MOCK_USER))
        assert result is None
