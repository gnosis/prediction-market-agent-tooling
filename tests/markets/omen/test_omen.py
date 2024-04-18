import numpy as np

from prediction_market_agent_tooling.gtypes import DatetimeWithTimezone
from prediction_market_agent_tooling.markets.agent_market import FilterBy, SortBy
from prediction_market_agent_tooling.markets.omen.omen import (
    OmenAgentMarket,
    pick_binary_market,
)
from prediction_market_agent_tooling.markets.omen.omen_subgraph_handler import (
    OmenSubgraphHandler,
)
from prediction_market_agent_tooling.tools.utils import check_not_none, utcnow


def test_omen_pick_binary_market() -> None:
    market = pick_binary_market()
    assert market.outcomes == [
        "Yes",
        "No",
    ], "Omen binary market should have two outcomes, Yes and No."


def test_p_yes() -> None:
    # Find a market with outcomeTokenMarginalPrices and verify that p_yes is correct.
    for m in OmenSubgraphHandler().get_omen_binary_markets_simple(
        limit=200,
        sort_by=SortBy.NEWEST,
        filter_by=FilterBy.OPEN,
    ):
        if m.outcomeTokenProbabilities is not None:
            market = m
            break
    assert market is not None, "No market found with outcomeTokenProbabilities."
    assert np.isclose(market.p_yes, check_not_none(market.outcomeTokenProbabilities)[0])


def test_omen_market_close_time() -> None:
    """
    Get open markets sorted by 'closing_soonest'. Verify that:
    - close time is after open time
    - close time is in the future
    - close time is in ascending order
    """
    time_now = utcnow()
    markets = [
        OmenAgentMarket.from_data_model(m)
        for m in OmenSubgraphHandler().get_omen_binary_markets_simple(
            limit=100,
            sort_by=SortBy.CLOSING_SOONEST,
            filter_by=FilterBy.OPEN,
        )
    ]
    for market in markets:
        assert (
            market.close_time > market.created_time
        ), "Market close time should be after open time."
        assert (
            market.close_time >= time_now
        ), "Market close time should be in the future."
        time_now = DatetimeWithTimezone(
            market.close_time
        )  # Ensure close time is in ascending order


def test_market_liquidity() -> None:
    """
    Get open markets sorted by 'closing soonest'. Verify that liquidity is
    greater than 0
    """
    markets = OmenAgentMarket.get_binary_markets(
        limit=10,
        sort_by=SortBy.CLOSING_SOONEST,
        filter_by=FilterBy.OPEN,
    )
    for market in markets:
        assert type(market) == OmenAgentMarket
        assert (
            market.get_liquidity_in_xdai() > 0
        ), "Market liquidity should be greater than 0."


def test_get_binary_market() -> None:
    id = "0x0020d13c89140b47e10db54cbd53852b90bc1391"
    market = OmenAgentMarket.get_binary_market(id)
    assert market.id == id
