from web3 import Web3

from prediction_market_agent_tooling.markets.polymarket.polymarket import (
    PolymarketAgentMarket,
)
from prediction_market_agent_tooling.tools.utils import DatetimeUTC

KNOWN_ACTIVE_USER = Web3.to_checksum_address(
    "0x4849c5c87f275016c25f39d0f37838a726db410b"
)

# Token ID for "Yes" on an active, high-volume Polymarket market.
KNOWN_ACTIVE_TOKEN_ID = (
    21742633143463906290569050155826241533067272736897614950488156847949938836455
)


def test_get_bets_made_since() -> None:
    start = DatetimeUTC.to_datetime_utc(0)
    bets = PolymarketAgentMarket.get_bets_made_since(KNOWN_ACTIVE_USER, start)

    assert len(bets) > 0
    for bet in bets:
        assert bet.market_id
        assert bet.market_question


def test_get_bets_made_since_sorted() -> None:
    start = DatetimeUTC.to_datetime_utc(0)
    bets = PolymarketAgentMarket.get_bets_made_since(KNOWN_ACTIVE_USER, start)

    for i in range(1, len(bets)):
        assert bets[i].created_time >= bets[i - 1].created_time


def test_get_last_trade_p_yes() -> None:
    markets = PolymarketAgentMarket.get_markets(limit=1)
    assert len(markets) > 0
    market = markets[0]

    p_yes = market.get_last_trade_p_yes()
    if p_yes is not None:
        assert 0 <= p_yes <= 1


def test_get_last_trade_p_no() -> None:
    markets = PolymarketAgentMarket.get_markets(limit=1)
    assert len(markets) > 0
    market = markets[0]

    p_no = market.get_last_trade_p_no()
    if p_no is not None:
        assert 0 <= p_no <= 1
