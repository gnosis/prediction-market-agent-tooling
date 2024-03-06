from datetime import datetime, timedelta

import pytest
import pytz

from prediction_market_agent_tooling.gtypes import mana_type
from prediction_market_agent_tooling.markets.manifold.api import (
    get_manifold_bets,
    get_manifold_binary_markets,
    get_resolved_manifold_bets,
    manifold_to_generic_resolved_bet,
    pick_binary_market,
    place_bet,
)
from tests.utils import RUN_PAID_TESTS


@pytest.fixture
def a_user_id() -> str:
    return "oCJrphq1RIT7fv3echpwOX8DTJV2"


@pytest.mark.skipif(not RUN_PAID_TESTS, reason="This test costs money to run.")
def test_manifold() -> None:
    market = pick_binary_market()
    print("Placing bet on market:", market.question)
    place_bet(mana_type(1), market.id, True)


def test_manifold_markets() -> None:
    limit = 2000
    markets = get_manifold_binary_markets(
        limit=limit, sort="newest", filter_="resolved"
    )
    assert len(markets) == limit


def test_manifold_bets(a_user_id: str) -> None:
    start_time = datetime(2020, 2, 1, tzinfo=pytz.UTC)
    bets = get_manifold_bets(
        user_id=a_user_id,
        start_time=start_time,
        end_time=None,
    )
    assert len(bets) > 0


def test_resolved_manifold_bets(a_user_id: str) -> None:
    start_time = datetime(2024, 2, 20, tzinfo=pytz.UTC)
    resolved_bets = get_resolved_manifold_bets(
        user_id=a_user_id,
        start_time=start_time,
        end_time=start_time + timedelta(days=1),
    )
    # Verify that the bets are unique.
    assert len(set([bet.id for bet in resolved_bets])) == len(resolved_bets)

    # Verify that all bets convert to generic resolved bets.
    for bet in resolved_bets:
        manifold_to_generic_resolved_bet(bet)
