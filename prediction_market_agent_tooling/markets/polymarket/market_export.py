import json
import typing as t
from collections.abc import Sequence

from pydantic import BaseModel

from prediction_market_agent_tooling.markets.agent_market import FilterBy, SortBy
from prediction_market_agent_tooling.markets.polymarket.polymarket import (
    PolymarketAgentMarket,
)
from prediction_market_agent_tooling.tools.datetime_utc import DatetimeUTC
from prediction_market_agent_tooling.tools.utils import utcnow


class MarketExportData(BaseModel):
    source: str = "polymarket"
    market_id: str
    condition_id: str
    question: str
    description: str | None
    outcomes: list[str]
    probabilities: dict[str, float]
    volume_usd: float | None
    liquidity_usd: float
    created_time: DatetimeUTC | None
    close_time: DatetimeUTC | None
    url: str
    resolution: str | None
    is_active: bool
    tags: list[str]
    exported_at: DatetimeUTC


def export_market(
    market: PolymarketAgentMarket,
    tags: list[str] | None = None,
) -> MarketExportData:
    resolution: str | None = None
    if market.resolution is not None and market.resolution.outcome is not None:
        resolution = str(market.resolution.outcome)

    return MarketExportData(
        market_id=market.id,
        condition_id=market.condition_id.to_0x_hex(),
        question=market.question,
        description=market.description,
        outcomes=[str(o) for o in market.outcomes],
        probabilities={str(k): float(v) for k, v in market.probabilities.items()},
        volume_usd=float(market.volume.value) if market.volume is not None else None,
        liquidity_usd=float(market.liquidity_usd.value),
        created_time=market.created_time,
        close_time=market.close_time,
        url=market.url,
        resolution=resolution,
        is_active=market.active_flag_from_polymarket
        and not market.closed_flag_from_polymarket,
        tags=tags if tags is not None else [],
        exported_at=utcnow(),
    )


def export_markets_batch(
    markets: Sequence[PolymarketAgentMarket],
    tags_by_market_id: dict[str, list[str]] | None = None,
) -> list[MarketExportData]:
    return [
        export_market(
            market,
            tags=(tags_by_market_id or {}).get(market.id),
        )
        for market in markets
    ]


def export_markets_to_json(
    markets: Sequence[PolymarketAgentMarket],
    output_path: str | None = None,
    tags_by_market_id: dict[str, list[str]] | None = None,
) -> str:
    exported = export_markets_batch(markets, tags_by_market_id)
    json_str = json.dumps(
        [m.model_dump(mode="json") for m in exported],
        indent=2,
    )
    if output_path is not None:
        with open(output_path, "w") as f:
            f.write(json_str)
    return json_str


def fetch_and_export_markets(
    limit: int = 100,
    filter_by: FilterBy = FilterBy.OPEN,
    sort_by: SortBy = SortBy.NONE,
    created_after: t.Optional[DatetimeUTC] = None,
) -> list[MarketExportData]:
    gamma_items, condition_dict, trading_fees = (
        PolymarketAgentMarket._fetch_gamma_markets_with_conditions_and_fees(
            limit=limit,
            sort_by=sort_by,
            filter_by=filter_by,
            created_after=created_after,
        )
    )

    results: list[MarketExportData] = []
    for item in gamma_items:
        agent_markets = PolymarketAgentMarket.from_data_model_all(
            item,
            condition_dict,
            trading_fee_rate=trading_fees[item.id],
        )
        tags = [tag.label for tag in item.tags]
        for market in agent_markets:
            results.append(export_market(market, tags=tags))

    return results
