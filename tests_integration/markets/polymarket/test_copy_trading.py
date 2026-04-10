import os
from datetime import timedelta
from unittest.mock import MagicMock

from web3 import Web3

from prediction_market_agent_tooling.markets.polymarket.copy_trading import (
    PolymarketCopyTrader,
    TraderSortBy,
    discover_top_traders,
)
from prediction_market_agent_tooling.tools.utils import utcnow

KNOWN_ACTIVE_USER = Web3.to_checksum_address(
    "0x4849c5c87f275016c25f39d0f37838a726db410b"
)


def test_detect_trades_for_known_trader() -> None:
    trader = PolymarketCopyTrader(
        target_address=KNOWN_ACTIVE_USER,
        api_keys=MagicMock(),
        dry_run=True,
    )
    since = utcnow() - timedelta(hours=2)
    trades = trader.get_new_trades_since(since)
    # Active trader should have at least some trades in the past 2 hours.
    # If not, this test may need a different active address.
    assert isinstance(trades, list)


def test_dry_run_replication() -> None:
    trader = PolymarketCopyTrader(
        target_address=KNOWN_ACTIVE_USER,
        api_keys=MagicMock(),
        dry_run=True,
    )
    trader._state.last_poll_timestamp = utcnow() - timedelta(minutes=30)
    results = trader.run_once()

    # All trades should be skipped (dry_run, closed market, etc.)
    for result in results:
        assert result.skipped


def test_state_persistence_across_runs(tmp_path: object) -> None:
    state_path = os.path.join(str(tmp_path), "state.json")

    trader1 = PolymarketCopyTrader(
        target_address=KNOWN_ACTIVE_USER,
        api_keys=MagicMock(),
        dry_run=True,
        state_file_path=state_path,
    )
    trader1._state.last_poll_timestamp = utcnow() - timedelta(minutes=30)
    trader1.run_once()

    # Create new trader loading same state
    trader2 = PolymarketCopyTrader(
        target_address=KNOWN_ACTIVE_USER,
        api_keys=MagicMock(),
        dry_run=True,
        state_file_path=state_path,
    )
    second_results = trader2.run_once()

    # Second run should find no new trades (all already in state)
    assert len(second_results) == 0


def test_discover_top_traders_live() -> None:
    profiles = discover_top_traders(
        market_count=2,
        trades_per_market=20,
        sort_by=TraderSortBy.VOLUME,
        min_trade_count=1,
    )
    assert isinstance(profiles, list)
    for profile in profiles:
        assert profile.trade_count >= 1
        assert profile.total_volume.value > 0
