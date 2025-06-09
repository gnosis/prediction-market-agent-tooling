from datetime import timedelta

import pytest

from prediction_market_agent_tooling.config import APIKeys
from prediction_market_agent_tooling.gtypes import Mana, OutcomeStr, OutcomeToken
from prediction_market_agent_tooling.loggers import logger
from prediction_market_agent_tooling.markets.manifold.api import (
    get_manifold_bets,
    get_manifold_binary_markets,
    get_manifold_market,
    get_one_manifold_binary_market,
    get_resolved_manifold_bets,
    manifold_to_generic_resolved_bet,
    place_bet,
)
from prediction_market_agent_tooling.markets.manifold.data_models import ManifoldPool
from prediction_market_agent_tooling.tools.utils import utc_datetime
from tests.utils import RUN_PAID_TESTS


@pytest.fixture
def a_user_id() -> str:
    return "oCJrphq1RIT7fv3echpwOX8DTJV2"


@pytest.mark.skipif(not RUN_PAID_TESTS, reason="This test costs money to run.")
def test_manifold() -> None:
    market = get_one_manifold_binary_market()
    logger.info("Placing bet on market:", market.question)
    place_bet(Mana(1), market.id, OutcomeStr("YES"), APIKeys().manifold_api_key)


def test_manifold_markets() -> None:
    limit = 2000
    markets = get_manifold_binary_markets(
        limit=limit, sort="newest", filter_="resolved"
    )
    assert len(markets) == limit


def test_manifold_full_market() -> None:
    markets = get_manifold_binary_markets(22)
    for market in markets:
        full_market = get_manifold_market(market.id)
        assert market.id == full_market.id, f"{market.id=} != {full_market.id=}"


def test_manifold_bets(a_user_id: str) -> None:
    start_time = utc_datetime(2020, 2, 1)
    bets = get_manifold_bets(
        user_id=a_user_id,
        start_time=start_time,
        end_time=None,
    )
    assert len(bets) > 0


def test_resolved_manifold_bets(a_user_id: str) -> None:
    start_time = utc_datetime(2024, 2, 20)
    resolved_bets, markets = get_resolved_manifold_bets(
        user_id=a_user_id,
        start_time=start_time,
        end_time=start_time + timedelta(days=1),
    )
    # Verify that the bets are unique.
    assert len(set([bet.id for bet in resolved_bets])) == len(resolved_bets)

    # Verify that all bets convert to generic resolved bets.
    for bet, market in zip(resolved_bets, markets):
        manifold_to_generic_resolved_bet(bet, market)


def test_manifold_pool() -> None:
    pool = ManifoldPool(NO=OutcomeToken(1), YES=OutcomeToken(2))
    assert pool.size_for_outcome("NO") == OutcomeToken(1.0)
    assert pool.size_for_outcome("YES") == OutcomeToken(2.0)

    with pytest.raises(ValueError) as e:
        pool.size_for_outcome("FOO")
    assert "Unexpected outcome string" in str(e.value)
