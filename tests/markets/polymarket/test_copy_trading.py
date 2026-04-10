from unittest.mock import MagicMock, patch

import pytest
from web3 import Web3

from prediction_market_agent_tooling.gtypes import (
    USD,
    ChecksumAddress,
    OutcomeStr,
    OutcomeToken,
)
from prediction_market_agent_tooling.markets.data_models import Resolution
from prediction_market_agent_tooling.markets.polymarket.copy_trading import (
    CopyTraderState,
    PolymarketCopyTrader,
    TraderSortBy,
    discover_top_traders,
)
from prediction_market_agent_tooling.markets.polymarket.data_models import (
    PolymarketTradeResponse,
)
from prediction_market_agent_tooling.tools.hexbytes_custom import HexBytes
from prediction_market_agent_tooling.tools.utils import DatetimeUTC

MOCK_TARGET: ChecksumAddress = Web3.to_checksum_address(
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


def _make_trade(**overrides: object) -> PolymarketTradeResponse:
    return PolymarketTradeResponse.model_validate(_make_trade_dict(**overrides))


def _make_copy_trader(**overrides: object) -> PolymarketCopyTrader:
    defaults: dict[str, object] = {
        "target_address": MOCK_TARGET,
        "api_keys": MagicMock(),
        "copy_ratio": 1.0,
        "min_trade_size": USD(1.0),
        "dry_run": False,
    }
    defaults.update(overrides)
    return PolymarketCopyTrader(**defaults)  # type: ignore[arg-type]


TX_HASH_A = "0x" + "aa" * 32
TX_HASH_B = "0x" + "bb" * 32
TX_HASH_C = "0x" + "cc" * 32


class TestGetNewTrades:
    @patch(
        "prediction_market_agent_tooling.markets.polymarket.copy_trading.get_user_trades"
    )
    def test_filters_already_replicated(self, mock_get_trades: MagicMock) -> None:
        trade1 = _make_trade(transactionHash=TX_HASH_A)
        trade2 = _make_trade(transactionHash=TX_HASH_B)
        trade3 = _make_trade(transactionHash=TX_HASH_C)
        mock_get_trades.return_value = [trade1, trade2, trade3]

        trader = _make_copy_trader()
        trader._state.replicated_tx_hashes = {TX_HASH_B}

        since = DatetimeUTC.to_datetime_utc(1699000000)
        result = trader.get_new_trades_since(since)

        assert len(result) == 2
        hashes = {r.transactionHash.to_0x_hex() for r in result}
        assert TX_HASH_B not in hashes

    @patch(
        "prediction_market_agent_tooling.markets.polymarket.copy_trading.get_user_trades"
    )
    def test_sorts_chronologically(self, mock_get_trades: MagicMock) -> None:
        trade_old = _make_trade(transactionHash=TX_HASH_A, timestamp=1700000000)
        trade_new = _make_trade(transactionHash=TX_HASH_B, timestamp=1700100000)
        trade_mid = _make_trade(transactionHash=TX_HASH_C, timestamp=1700050000)
        mock_get_trades.return_value = [trade_new, trade_old, trade_mid]

        trader = _make_copy_trader()
        result = trader.get_new_trades_since(DatetimeUTC.to_datetime_utc(1699000000))

        assert result[0].transactionHash.to_0x_hex() == TX_HASH_A
        assert result[1].transactionHash.to_0x_hex() == TX_HASH_C
        assert result[2].transactionHash.to_0x_hex() == TX_HASH_B

    @patch(
        "prediction_market_agent_tooling.markets.polymarket.copy_trading.get_user_trades"
    )
    def test_empty_when_all_replicated(self, mock_get_trades: MagicMock) -> None:
        trade1 = _make_trade(transactionHash=TX_HASH_A)
        trade2 = _make_trade(transactionHash=TX_HASH_B)
        mock_get_trades.return_value = [trade1, trade2]

        trader = _make_copy_trader()
        trader._state.replicated_tx_hashes = {TX_HASH_A, TX_HASH_B}

        result = trader.get_new_trades_since(DatetimeUTC.to_datetime_utc(1699000000))
        assert len(result) == 0


class TestReplicateTrade:
    @patch(
        "prediction_market_agent_tooling.markets.polymarket.copy_trading.PolymarketAgentMarket.get_trade_balance"
    )
    @patch(
        "prediction_market_agent_tooling.markets.polymarket.copy_trading.PolymarketAgentMarket.get_binary_market"
    )
    def test_buy_scales_by_ratio(
        self,
        mock_get_market: MagicMock,
        mock_get_balance: MagicMock,
    ) -> None:
        mock_market = MagicMock()
        mock_market.can_be_traded.return_value = True
        mock_market.place_bet.return_value = "0xtx_hash"
        mock_get_market.return_value = mock_market
        mock_get_balance.return_value = USD(1000)

        trade = _make_trade(size=100.0, price=0.6, side="BUY")
        trader = _make_copy_trader(copy_ratio=0.5)

        result = trader.replicate_trade(trade)

        assert not result.skipped
        expected_usd = 100.0 * 0.6 * 0.5  # 30.0
        mock_market.place_bet.assert_called_once()
        call_args = mock_market.place_bet.call_args
        assert call_args.kwargs["amount"] == USD(expected_usd)

    @patch(
        "prediction_market_agent_tooling.markets.polymarket.copy_trading.PolymarketAgentMarket.get_binary_market"
    )
    def test_sell_scales_by_ratio(
        self,
        mock_get_market: MagicMock,
    ) -> None:
        mock_market = MagicMock()
        mock_market.can_be_traded.return_value = True
        mock_market.get_token_balance.return_value = OutcomeToken(500)
        mock_market.sell_tokens.return_value = "0xtx_hash"
        mock_get_market.return_value = mock_market

        trade = _make_trade(size=100.0, price=0.6, side="SELL")
        trader = _make_copy_trader(copy_ratio=2.0)

        result = trader.replicate_trade(trade)

        assert not result.skipped
        mock_market.sell_tokens.assert_called_once()
        call_args = mock_market.sell_tokens.call_args
        assert call_args.kwargs["amount"] == OutcomeToken(200.0)

    @patch(
        "prediction_market_agent_tooling.markets.polymarket.copy_trading.PolymarketAgentMarket.get_trade_balance"
    )
    @patch(
        "prediction_market_agent_tooling.markets.polymarket.copy_trading.PolymarketAgentMarket.get_binary_market"
    )
    def test_buy_below_min_size_skipped(
        self,
        mock_get_market: MagicMock,
        mock_get_balance: MagicMock,
    ) -> None:
        mock_market = MagicMock()
        mock_market.can_be_traded.return_value = True
        mock_get_market.return_value = mock_market

        trade = _make_trade(size=1.0, price=0.5, side="BUY")  # cost = 0.5 USD
        trader = _make_copy_trader(min_trade_size=USD(5.0))

        result = trader.replicate_trade(trade)

        assert result.skipped
        assert "below minimum" in (result.skip_reason or "")

    @patch(
        "prediction_market_agent_tooling.markets.polymarket.copy_trading.PolymarketAgentMarket.get_binary_market"
    )
    def test_closed_market_skipped(self, mock_get_market: MagicMock) -> None:
        mock_market = MagicMock()
        mock_market.can_be_traded.return_value = False
        mock_get_market.return_value = mock_market

        trade = _make_trade()
        trader = _make_copy_trader()

        result = trader.replicate_trade(trade)

        assert result.skipped
        assert "not tradeable" in (result.skip_reason or "")

    @patch(
        "prediction_market_agent_tooling.markets.polymarket.copy_trading.PolymarketAgentMarket.get_trade_balance"
    )
    @patch(
        "prediction_market_agent_tooling.markets.polymarket.copy_trading.PolymarketAgentMarket.get_binary_market"
    )
    def test_insufficient_balance_skipped(
        self,
        mock_get_market: MagicMock,
        mock_get_balance: MagicMock,
    ) -> None:
        mock_market = MagicMock()
        mock_market.can_be_traded.return_value = True
        mock_get_market.return_value = mock_market
        mock_get_balance.return_value = USD(0.5)

        trade = _make_trade(size=100.0, price=0.6, side="BUY")  # cost = 60 USD
        trader = _make_copy_trader()

        result = trader.replicate_trade(trade)

        assert result.skipped
        assert "Insufficient balance" in (result.skip_reason or "")

    @patch(
        "prediction_market_agent_tooling.markets.polymarket.copy_trading.PolymarketAgentMarket.get_binary_market"
    )
    def test_market_lookup_failure_skipped(self, mock_get_market: MagicMock) -> None:
        mock_get_market.side_effect = ValueError("Market not found")

        trade = _make_trade()
        trader = _make_copy_trader()

        result = trader.replicate_trade(trade)

        assert result.skipped
        assert "Market lookup failed" in (result.skip_reason or "")

    @patch(
        "prediction_market_agent_tooling.markets.polymarket.copy_trading.PolymarketAgentMarket.get_binary_market"
    )
    def test_sell_no_position_skipped(self, mock_get_market: MagicMock) -> None:
        mock_market = MagicMock()
        mock_market.can_be_traded.return_value = True
        mock_market.get_token_balance.return_value = OutcomeToken(0)
        mock_get_market.return_value = mock_market

        trade = _make_trade(side="SELL")
        trader = _make_copy_trader()

        result = trader.replicate_trade(trade)

        assert result.skipped
        assert "No position" in (result.skip_reason or "")

    @patch(
        "prediction_market_agent_tooling.markets.polymarket.copy_trading.PolymarketAgentMarket.get_trade_balance"
    )
    @patch(
        "prediction_market_agent_tooling.markets.polymarket.copy_trading.PolymarketAgentMarket.get_binary_market"
    )
    def test_dry_run_no_execution(
        self,
        mock_get_market: MagicMock,
        mock_get_balance: MagicMock,
    ) -> None:
        mock_market = MagicMock()
        mock_market.can_be_traded.return_value = True
        mock_get_market.return_value = mock_market
        mock_get_balance.return_value = USD(1000)

        trade = _make_trade()
        trader = _make_copy_trader(dry_run=True)

        result = trader.replicate_trade(trade)

        assert result.skipped
        assert result.skip_reason == "dry_run"
        mock_market.place_bet.assert_not_called()
        mock_market.sell_tokens.assert_not_called()


class TestRunOnce:
    @patch("prediction_market_agent_tooling.markets.polymarket.copy_trading.utcnow")
    @patch(
        "prediction_market_agent_tooling.markets.polymarket.copy_trading.get_user_trades"
    )
    def test_updates_timestamp(
        self, mock_get_trades: MagicMock, mock_utcnow: MagicMock
    ) -> None:
        mock_get_trades.return_value = []
        now = DatetimeUTC.to_datetime_utc(1700200000)
        mock_utcnow.return_value = now

        trader = _make_copy_trader()
        trader.run_once()

        assert trader._state.last_poll_timestamp == now

    @patch(
        "prediction_market_agent_tooling.markets.polymarket.copy_trading.PolymarketAgentMarket.get_trade_balance"
    )
    @patch(
        "prediction_market_agent_tooling.markets.polymarket.copy_trading.PolymarketAgentMarket.get_binary_market"
    )
    @patch("prediction_market_agent_tooling.markets.polymarket.copy_trading.utcnow")
    @patch(
        "prediction_market_agent_tooling.markets.polymarket.copy_trading.get_user_trades"
    )
    def test_records_hashes(
        self,
        mock_get_trades: MagicMock,
        mock_utcnow: MagicMock,
        mock_get_market: MagicMock,
        mock_get_balance: MagicMock,
    ) -> None:
        trade1 = _make_trade(transactionHash=TX_HASH_A)
        trade2 = _make_trade(transactionHash=TX_HASH_B)
        mock_get_trades.return_value = [trade1, trade2]
        mock_utcnow.return_value = DatetimeUTC.to_datetime_utc(1700200000)

        mock_market = MagicMock()
        mock_market.can_be_traded.return_value = True
        mock_market.place_bet.return_value = "0xtx"
        mock_get_market.return_value = mock_market
        mock_get_balance.return_value = USD(1000)

        trader = _make_copy_trader()
        trader.run_once()

        assert TX_HASH_A in trader._state.replicated_tx_hashes
        assert TX_HASH_B in trader._state.replicated_tx_hashes


class TestState:
    def test_save_load_roundtrip(self, tmp_path: object) -> None:
        import os

        path = os.path.join(str(tmp_path), "state.json")
        state = CopyTraderState(
            replicated_tx_hashes={"0xaaa", "0xbbb"},
            last_poll_timestamp=DatetimeUTC.to_datetime_utc(1700000000),
        )
        state.save(path)

        loaded = CopyTraderState.load(path)
        assert loaded.replicated_tx_hashes == {"0xaaa", "0xbbb"}
        assert loaded.last_poll_timestamp == state.last_poll_timestamp

    def test_empty_factory(self) -> None:
        state = CopyTraderState.empty()
        assert len(state.replicated_tx_hashes) == 0
        assert state.last_poll_timestamp is None


class TestValidation:
    def test_copy_ratio_must_be_positive(self) -> None:
        with pytest.raises(ValueError, match="copy_ratio must be positive"):
            _make_copy_trader(copy_ratio=0)

        with pytest.raises(ValueError, match="copy_ratio must be positive"):
            _make_copy_trader(copy_ratio=-1.0)


class TestDiscoverTopTraders:
    @patch(
        "prediction_market_agent_tooling.markets.polymarket.copy_trading.PolymarketSubgraphHandler"
    )
    @patch(
        "prediction_market_agent_tooling.markets.polymarket.copy_trading.PolymarketAgentMarket.build_resolution_from_condition"
    )
    @patch(
        "prediction_market_agent_tooling.markets.polymarket.copy_trading.get_trades_for_market"
    )
    @patch(
        "prediction_market_agent_tooling.markets.polymarket.copy_trading.get_polymarkets_with_pagination"
    )
    def test_aggregates_pnl(
        self,
        mock_get_markets: MagicMock,
        mock_get_trades: MagicMock,
        mock_build_resolution: MagicMock,
        mock_subgraph_cls: MagicMock,
    ) -> None:
        # Set up market
        mock_gamma_market = MagicMock()
        mock_gamma_market.conditionId = MOCK_CONDITION_ID
        mock_gamma_item = MagicMock()
        mock_gamma_item.markets = [mock_gamma_market]
        mock_get_markets.return_value = [mock_gamma_item]

        # Trader A: 2 winning BUY trades
        # Trader B: 1 losing BUY trade
        trade_a1 = _make_trade(
            proxyWallet="0x000000000000000000000000000000000000000A",
            transactionHash="0xa1",
            size=100.0,
            price=0.6,
            outcome="Yes",
        )
        trade_a2 = _make_trade(
            proxyWallet="0x000000000000000000000000000000000000000A",
            transactionHash="0xa2",
            size=50.0,
            price=0.7,
            outcome="Yes",
        )
        trade_b1 = _make_trade(
            proxyWallet="0x000000000000000000000000000000000000000b",
            transactionHash="0xb1",
            size=80.0,
            price=0.5,
            outcome="No",
        )
        mock_get_trades.return_value = [trade_a1, trade_a2, trade_b1]

        # Set up resolution: "Yes" wins
        resolution = Resolution(outcome=OutcomeStr("Yes"), invalid=False)
        mock_build_resolution.return_value = resolution
        mock_subgraph_cls.return_value.get_conditions.return_value = []

        profiles = discover_top_traders(
            market_count=1, min_trade_count=1, sort_by=TraderSortBy.PNL
        )

        # Trader A should have positive PnL (bought Yes, Yes won)
        # Trader B should have negative PnL (bought No, Yes won)
        assert len(profiles) >= 2
        trader_a = next(
            p
            for p in profiles
            if p.address
            == Web3.to_checksum_address("0x000000000000000000000000000000000000000A")
        )
        assert trader_a.total_pnl.value > 0
        assert trader_a.resolved_trade_count == 2

    @patch(
        "prediction_market_agent_tooling.markets.polymarket.copy_trading.PolymarketSubgraphHandler"
    )
    @patch(
        "prediction_market_agent_tooling.markets.polymarket.copy_trading.PolymarketAgentMarket.build_resolution_from_condition"
    )
    @patch(
        "prediction_market_agent_tooling.markets.polymarket.copy_trading.get_trades_for_market"
    )
    @patch(
        "prediction_market_agent_tooling.markets.polymarket.copy_trading.get_polymarkets_with_pagination"
    )
    def test_roi_and_win_rate(
        self,
        mock_get_markets: MagicMock,
        mock_get_trades: MagicMock,
        mock_build_resolution: MagicMock,
        mock_subgraph_cls: MagicMock,
    ) -> None:
        mock_gamma_market = MagicMock()
        mock_gamma_market.conditionId = MOCK_CONDITION_ID
        mock_gamma_item = MagicMock()
        mock_gamma_item.markets = [mock_gamma_market]
        mock_get_markets.return_value = [mock_gamma_item]

        # 2 winning trades, 1 losing trade for same trader
        trades = [
            _make_trade(
                proxyWallet="0x0000000000000000000000000000000000000001",
                transactionHash=f"0x{i}",
                size=100.0,
                price=0.5,
                outcome="Yes" if i < 2 else "No",
            )
            for i in range(3)
        ]
        mock_get_trades.return_value = trades

        resolution = Resolution(outcome=OutcomeStr("Yes"), invalid=False)
        mock_build_resolution.return_value = resolution
        mock_subgraph_cls.return_value.get_conditions.return_value = []

        profiles = discover_top_traders(
            market_count=1, min_trade_count=1, sort_by=TraderSortBy.WIN_RATE
        )

        assert len(profiles) == 1
        profile = profiles[0]
        # 2 wins out of 3 resolved trades
        assert profile.win_rate == pytest.approx(2 / 3, abs=0.01)
        assert profile.resolved_trade_count == 3

    @patch(
        "prediction_market_agent_tooling.markets.polymarket.copy_trading.PolymarketSubgraphHandler"
    )
    @patch(
        "prediction_market_agent_tooling.markets.polymarket.copy_trading.PolymarketAgentMarket.build_resolution_from_condition"
    )
    @patch(
        "prediction_market_agent_tooling.markets.polymarket.copy_trading.get_trades_for_market"
    )
    @patch(
        "prediction_market_agent_tooling.markets.polymarket.copy_trading.get_polymarkets_with_pagination"
    )
    def test_min_trades_filter(
        self,
        mock_get_markets: MagicMock,
        mock_get_trades: MagicMock,
        mock_build_resolution: MagicMock,
        mock_subgraph_cls: MagicMock,
    ) -> None:
        mock_gamma_market = MagicMock()
        mock_gamma_market.conditionId = MOCK_CONDITION_ID
        mock_gamma_item = MagicMock()
        mock_gamma_item.markets = [mock_gamma_market]
        mock_get_markets.return_value = [mock_gamma_item]

        # Trader with only 1 trade (below min_trade_count=5)
        mock_get_trades.return_value = [
            _make_trade(
                proxyWallet="0x0000000000000000000000000000000000000001",
                transactionHash="0x1",
            )
        ]

        mock_build_resolution.return_value = None
        mock_subgraph_cls.return_value.get_conditions.return_value = []

        profiles = discover_top_traders(
            market_count=1, min_trade_count=5, sort_by=TraderSortBy.VOLUME
        )

        assert len(profiles) == 0

    @patch(
        "prediction_market_agent_tooling.markets.polymarket.copy_trading.PolymarketSubgraphHandler"
    )
    @patch(
        "prediction_market_agent_tooling.markets.polymarket.copy_trading.PolymarketAgentMarket.build_resolution_from_condition"
    )
    @patch(
        "prediction_market_agent_tooling.markets.polymarket.copy_trading.get_trades_for_market"
    )
    @patch(
        "prediction_market_agent_tooling.markets.polymarket.copy_trading.get_polymarkets_with_pagination"
    )
    def test_sorts_by_metric(
        self,
        mock_get_markets: MagicMock,
        mock_get_trades: MagicMock,
        mock_build_resolution: MagicMock,
        mock_subgraph_cls: MagicMock,
    ) -> None:
        mock_gamma_market = MagicMock()
        mock_gamma_market.conditionId = MOCK_CONDITION_ID
        mock_gamma_item = MagicMock()
        mock_gamma_item.markets = [mock_gamma_market]
        mock_get_markets.return_value = [mock_gamma_item]

        # Two traders with different volumes
        trades = []
        for i in range(3):
            trades.append(
                _make_trade(
                    proxyWallet="0x0000000000000000000000000000000000000001",
                    transactionHash=f"0xa{i}",
                    size=10.0,
                    price=0.5,
                )
            )
        for i in range(3):
            trades.append(
                _make_trade(
                    proxyWallet="0x0000000000000000000000000000000000000002",
                    transactionHash=f"0xb{i}",
                    size=100.0,
                    price=0.5,
                )
            )
        mock_get_trades.return_value = trades

        mock_build_resolution.return_value = None
        mock_subgraph_cls.return_value.get_conditions.return_value = []

        profiles = discover_top_traders(
            market_count=1, min_trade_count=1, sort_by=TraderSortBy.VOLUME
        )

        assert len(profiles) == 2
        # Higher volume trader should be first
        assert profiles[0].total_volume.value > profiles[1].total_volume.value
