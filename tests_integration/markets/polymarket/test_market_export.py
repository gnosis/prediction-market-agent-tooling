import json

import pytest

from prediction_market_agent_tooling.markets.agent_market import FilterBy, SortBy
from prediction_market_agent_tooling.markets.polymarket.market_export import (
    MarketExportData,
    fetch_and_export_markets,
)


@pytest.mark.parametrize("limit", [5])
def test_fetch_and_export_markets(limit: int) -> None:
    exported = fetch_and_export_markets(limit=limit, filter_by=FilterBy.OPEN)

    assert len(exported) == limit
    for item in exported:
        assert item.source == "polymarket"
        assert item.question
        assert item.url
        assert item.market_id
        assert item.condition_id.startswith("0x")
        assert item.exported_at is not None


def test_fetch_and_export_markets_large_batch() -> None:
    exported = fetch_and_export_markets(limit=100, filter_by=FilterBy.OPEN)
    assert len(exported) == 100


def test_fetch_and_export_probability_validation() -> None:
    exported = fetch_and_export_markets(limit=20, filter_by=FilterBy.OPEN)

    for item in exported:
        prob_sum = sum(item.probabilities.values())
        assert (
            0.99 <= prob_sum <= 1.01
        ), f"Probability sum {prob_sum} out of range for market {item.market_id}"


def test_fetch_and_export_markets_resolved() -> None:
    exported = fetch_and_export_markets(
        limit=10,
        filter_by=FilterBy.RESOLVED,
        sort_by=SortBy.NEWEST,
    )

    assert len(exported) > 0
    for item in exported:
        assert item.resolution is not None


def test_fetch_and_export_markets_tags_populated() -> None:
    exported = fetch_and_export_markets(limit=10, filter_by=FilterBy.OPEN)
    has_tags = any(len(item.tags) > 0 for item in exported)
    assert has_tags, "Expected at least some markets to have tags"


def test_fetch_and_export_json_roundtrip() -> None:
    exported = fetch_and_export_markets(limit=10, filter_by=FilterBy.OPEN)
    json_str = json.dumps(
        [m.model_dump(mode="json") for m in exported],
        indent=2,
    )
    parsed = json.loads(json_str)

    for item in parsed:
        restored = MarketExportData.model_validate(item)
        assert restored.source == "polymarket"
        assert restored.market_id


def test_fetch_and_export_multi_inner_market() -> None:
    """Export with multi-inner-market events included.

    Fetches events (including multi-inner-market ones) and verifies that
    all inner markets are exported with unique market_ids and valid data.
    """
    from prediction_market_agent_tooling.markets.polymarket.api import (
        get_polymarkets_with_pagination,
    )
    from prediction_market_agent_tooling.markets.polymarket.polymarket import (
        PolymarketAgentMarket,
    )
    from prediction_market_agent_tooling.markets.polymarket.polymarket_subgraph_handler import (
        PolymarketSubgraphHandler,
    )
    from prediction_market_agent_tooling.tools.hexbytes_custom import HexBytes

    gamma_items = get_polymarkets_with_pagination(
        limit=200,
        only_binary=False,
    )

    multi_events = [
        item
        for item in gamma_items
        if item.markets is not None and len(item.markets) > 1
    ]
    assert len(multi_events) > 0, "Expected at least one multi-inner-market event"

    # Collect all condition_ids across all inner markets
    all_condition_ids: set[HexBytes] = set()
    for item in multi_events[:5]:
        for inner in item.markets:
            all_condition_ids.add(inner.conditionId)

    conditions = PolymarketSubgraphHandler().get_conditions(list(all_condition_ids))
    condition_dict = {c.id: c for c in conditions}

    # Export all inner markets from the first few multi-events
    from prediction_market_agent_tooling.markets.polymarket.market_export import (
        export_market,
    )

    exported_items: list[MarketExportData] = []
    for item in multi_events[:5]:
        agent_markets = PolymarketAgentMarket.from_data_model_all(
            item, condition_dict, trading_fee_rate=0
        )
        for market in agent_markets:
            exported_items.append(export_market(market))

    assert (
        len(exported_items) >= 2
    ), f"Expected at least 2 exported items, got {len(exported_items)}"

    # All should have unique market_ids
    market_ids = [e.market_id for e in exported_items]
    assert len(market_ids) == len(set(market_ids)), "Exported market_ids must be unique"

    for exported in exported_items:
        assert exported.source == "polymarket"
        assert exported.condition_id.startswith("0x")
        assert exported.market_id.startswith("0x")
        assert exported.question
        assert len(exported.outcomes) >= 2
        prob_sum = sum(exported.probabilities.values())
        assert (
            0.99 <= prob_sum <= 1.01
        ), f"Probability sum {prob_sum} out of range for {exported.market_id}"
