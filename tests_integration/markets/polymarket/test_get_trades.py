from web3 import Web3

from prediction_market_agent_tooling.markets.polymarket.api import (
    get_trades_for_market,
    get_user_trades,
)
from prediction_market_agent_tooling.tools.hexbytes_custom import HexBytes

KNOWN_ACTIVE_USER = Web3.to_checksum_address(
    "0x4849c5c87f275016c25f39d0f37838a726db410b"
)
UNUSED_ADDRESS = Web3.to_checksum_address("0x0000000000000000000000000000000000000001")


def test_get_user_trades() -> None:
    trades = get_user_trades(user_address=KNOWN_ACTIVE_USER, limit=5)

    assert len(trades) > 0
    assert len(trades) <= 5
    for trade in trades:
        assert trade.side in {"BUY", "SELL"}
        assert trade.size > 0
        assert 0 <= trade.price <= 1
        assert trade.conditionId
        assert trade.title


def test_get_user_trades_pagination_consistency() -> None:
    small = get_user_trades(user_address=KNOWN_ACTIVE_USER, limit=3)
    large = get_user_trades(user_address=KNOWN_ACTIVE_USER, limit=10)

    assert len(small) <= 3
    assert len(large) <= 10
    for s, l in zip(small, large):
        assert s.transactionHash == l.transactionHash


def test_get_user_trades_empty_for_unknown_user() -> None:
    trades = get_user_trades(user_address=UNUSED_ADDRESS)
    assert trades == []


def test_get_trades_for_market() -> None:
    user_trades = get_user_trades(user_address=KNOWN_ACTIVE_USER, limit=1)
    assert len(user_trades) > 0

    condition_id = HexBytes(user_trades[0].conditionId)
    market_trades = get_trades_for_market(market=condition_id)

    assert len(market_trades) > 0
    for trade in market_trades:
        assert trade.conditionId == condition_id.to_0x_hex()


def test_get_trades_for_market_with_user() -> None:
    user_trades = get_user_trades(user_address=KNOWN_ACTIVE_USER, limit=1)
    assert len(user_trades) > 0

    condition_id = HexBytes(user_trades[0].conditionId)
    filtered = get_trades_for_market(market=condition_id, user=KNOWN_ACTIVE_USER)

    assert len(filtered) > 0
    for trade in filtered:
        assert trade.conditionId == condition_id.to_0x_hex()
