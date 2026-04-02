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
