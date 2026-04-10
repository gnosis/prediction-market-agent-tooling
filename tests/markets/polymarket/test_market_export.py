import json
from datetime import timedelta

from prediction_market_agent_tooling.gtypes import USD, OutcomeStr, Probability
from prediction_market_agent_tooling.markets.data_models import Resolution
from prediction_market_agent_tooling.markets.market_fees import MarketFees
from prediction_market_agent_tooling.markets.polymarket.market_export import (
    MarketExportData,
    export_market,
    export_markets_batch,
    export_markets_to_json,
)
from prediction_market_agent_tooling.markets.polymarket.polymarket import (
    PolymarketAgentMarket,
)
from prediction_market_agent_tooling.tools.utils import utcnow
from tests.markets.polymarket.conftest import MOCK_CONDITION_ID


def _make_market(**overrides: object) -> PolymarketAgentMarket:
    now = utcnow()
    defaults: dict[str, object] = {
        "id": MOCK_CONDITION_ID.to_0x_hex(),
        "event_id": "1",
        "description": "Test description",
        "volume": None,
        "url": "https://polymarket.com/event/test",
        "question": "Will GNO go up?",
        "outcomes": [OutcomeStr("Yes"), OutcomeStr("No")],
        "probabilities": {
            OutcomeStr("Yes"): Probability(0.6),
            OutcomeStr("No"): Probability(0.4),
        },
        "close_time": now + timedelta(hours=48),
        "resolution": None,
        "created_time": now - timedelta(hours=48),
        "outcome_token_pool": None,
        "condition_id": MOCK_CONDITION_ID,
        "liquidity_usd": USD(10),
        "token_ids": [111, 222],
        "closed_flag_from_polymarket": False,
        "active_flag_from_polymarket": True,
        "fees": MarketFees.get_zero_fees(),
    }
    defaults.update(overrides)
    return PolymarketAgentMarket(**defaults)  # type: ignore[arg-type]


def test_export_market_field_mapping() -> None:
    market = _make_market()
    exported = export_market(market)

    assert exported.source == "polymarket"
    assert exported.market_id == MOCK_CONDITION_ID.to_0x_hex()
    assert exported.condition_id == MOCK_CONDITION_ID.to_0x_hex()
    assert exported.question == "Will GNO go up?"
    assert exported.description == "Test description"
    assert exported.outcomes == ["Yes", "No"]
    assert exported.probabilities == {"Yes": 0.6, "No": 0.4}
    assert exported.volume_usd is None
    assert exported.liquidity_usd == 10.0
    assert exported.url == "https://polymarket.com/event/test"
    assert exported.resolution is None
    assert exported.is_active is True
    assert exported.tags == []
    assert exported.exported_at is not None


def test_export_market_with_tags() -> None:
    market = _make_market()
    exported = export_market(market, tags=["politics", "crypto"])
    assert exported.tags == ["politics", "crypto"]


def test_export_market_no_tags() -> None:
    market = _make_market()
    exported = export_market(market)
    assert exported.tags == []


def test_export_market_none_fields() -> None:
    market = _make_market(
        description=None,
        volume=None,
        created_time=None,
        close_time=None,
        resolution=None,
    )
    exported = export_market(market)

    assert exported.description is None
    assert exported.volume_usd is None
    assert exported.created_time is None
    assert exported.close_time is None
    assert exported.resolution is None


def test_export_market_resolved() -> None:
    market = _make_market(
        resolution=Resolution.from_answer(OutcomeStr("Yes")),
    )
    exported = export_market(market)
    assert exported.resolution == "Yes"


def test_export_market_resolved_invalid() -> None:
    market = _make_market(
        resolution=Resolution(outcome=None, invalid=True),
    )
    exported = export_market(market)
    assert exported.resolution is None


def test_export_market_inactive() -> None:
    market = _make_market(closed_flag_from_polymarket=True)
    exported = export_market(market)
    assert exported.is_active is False


def test_export_markets_batch() -> None:
    markets = [_make_market(id=f"id-{i}") for i in range(3)]
    exported = export_markets_batch(markets)

    assert len(exported) == 3
    assert [e.market_id for e in exported] == ["id-0", "id-1", "id-2"]


def test_export_markets_batch_with_tags() -> None:
    m1 = _make_market(id="id-1")
    m2 = _make_market(id="id-2")
    exported = export_markets_batch(
        [m1, m2],
        tags_by_market_id={"id-1": ["crypto"]},
    )

    assert exported[0].tags == ["crypto"]
    assert exported[1].tags == []


def test_export_markets_to_json_valid() -> None:
    markets = [_make_market()]
    json_str = export_markets_to_json(markets)
    parsed = json.loads(json_str)

    assert isinstance(parsed, list)
    assert len(parsed) == 1
    expected_keys = {
        "source",
        "market_id",
        "condition_id",
        "question",
        "description",
        "outcomes",
        "probabilities",
        "volume_usd",
        "liquidity_usd",
        "created_time",
        "close_time",
        "url",
        "resolution",
        "is_active",
        "tags",
        "exported_at",
    }
    assert set(parsed[0].keys()) == expected_keys


def test_export_markets_to_json_roundtrip() -> None:
    markets = [_make_market(), _make_market(id="id-2")]
    json_str = export_markets_to_json(markets)
    parsed = json.loads(json_str)

    for item in parsed:
        restored = MarketExportData.model_validate(item)
        assert restored.source == "polymarket"
        assert restored.market_id in (MOCK_CONDITION_ID.to_0x_hex(), "id-2")


def test_export_markets_to_json_file_output(tmp_path: object) -> None:
    from pathlib import Path

    output_file = Path(str(tmp_path)) / "export.json"
    markets = [_make_market()]
    json_str = export_markets_to_json(markets, output_path=str(output_file))

    assert output_file.exists()
    assert output_file.read_text() == json_str


def test_export_market_probability_types() -> None:
    market = _make_market()
    exported = export_market(market)

    for value in exported.probabilities.values():
        assert type(value) is float


def test_export_market_condition_id_format() -> None:
    market = _make_market()
    exported = export_market(market)
    assert exported.condition_id.startswith("0x")
