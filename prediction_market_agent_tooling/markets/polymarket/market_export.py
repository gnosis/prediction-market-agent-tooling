import json
import typing as t
from collections.abc import Sequence

from pydantic import BaseModel

from prediction_market_agent_tooling.markets.agent_market import FilterBy, SortBy
from prediction_market_agent_tooling.markets.polymarket.api import (
    PolymarketOrderByEnum,
    get_polymarkets_with_pagination,
)
from prediction_market_agent_tooling.markets.polymarket.polymarket import (
    PolymarketAgentMarket,
)
from prediction_market_agent_tooling.markets.polymarket.polymarket_subgraph_handler import (
    PolymarketSubgraphHandler,
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
    # Translate filter_by to Polymarket's closed parameter
    closed: bool | None
    if filter_by == FilterBy.OPEN:
        closed = False
    elif filter_by == FilterBy.RESOLVED:
        closed = True
    elif filter_by == FilterBy.NONE:
        closed = None
    else:
        raise ValueError(f"Unknown filter_by: {filter_by}")

    # Translate sort_by to Polymarket's order_by + ascending
    ascending: bool = False
    match sort_by:
        case SortBy.NEWEST:
            order_by = PolymarketOrderByEnum.START_DATE
            ascending = False
        case SortBy.CLOSING_SOONEST:
            ascending = True
            order_by = PolymarketOrderByEnum.END_DATE
        case SortBy.HIGHEST_LIQUIDITY:
            order_by = PolymarketOrderByEnum.LIQUIDITY
        case SortBy.NONE:
            order_by = PolymarketOrderByEnum.VOLUME_24HR
        case _:
            raise ValueError(f"Unknown sort_by: {sort_by}")

    gamma_items = get_polymarkets_with_pagination(
        limit=limit,
        closed=closed,
        order_by=order_by,
        ascending=ascending,
        created_after=created_after,
    )

    condition_ids = list(
        {
            item.markets[0].conditionId
            for item in gamma_items
            if item.markets is not None
        }
    )
    condition_models = PolymarketSubgraphHandler().get_conditions(condition_ids)
    condition_dict = {c.id: c for c in condition_models}

    results: list[MarketExportData] = []
    for item in gamma_items:
        market = PolymarketAgentMarket.from_data_model(item, condition_dict)
        if market is None:
            continue
        tags = [tag.label for tag in item.tags]
        results.append(export_market(market, tags=tags))

    return results
