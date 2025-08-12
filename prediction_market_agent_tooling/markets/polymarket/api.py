import typing as t
from datetime import timedelta
from enum import Enum
from urllib.parse import urljoin

import httpx
import tenacity

from prediction_market_agent_tooling.gtypes import ChecksumAddress, HexBytes
from prediction_market_agent_tooling.loggers import logger
from prediction_market_agent_tooling.markets.polymarket.data_models import (
    POLYMARKET_FALSE_OUTCOME,
    POLYMARKET_TRUE_OUTCOME,
    PolymarketGammaResponse,
    PolymarketGammaResponseDataItem,
    PolymarketPositionResponse,
)
from prediction_market_agent_tooling.tools.datetime_utc import DatetimeUTC
from prediction_market_agent_tooling.tools.httpx_cached_client import HttpxCachedClient
from prediction_market_agent_tooling.tools.utils import response_to_model

MARKETS_LIMIT = 100  # Polymarket will only return up to 100 markets
POLYMARKET_GAMMA_API_BASE_URL = "https://gamma-api.polymarket.com/"


class PolymarketOrderByEnum(str, Enum):
    LIQUIDITY = "liquidity"
    START_DATE = "startDate"
    END_DATE = "endDate"
    VOLUME_24HR = "volume24hr"


@tenacity.retry(
    stop=tenacity.stop_after_attempt(2),
    wait=tenacity.wait_fixed(1),
    after=lambda x: logger.debug(
        f"get_polymarkets_with_pagination failed, {x.attempt_number=}."
    ),
)
def get_polymarkets_with_pagination(
    limit: int,
    created_after: t.Optional[DatetimeUTC] = None,
    active: bool | None = None,
    closed: bool | None = None,
    excluded_questions: set[str] | None = None,
    only_binary: bool = True,
    archived: bool = False,
    ascending: bool = False,
    order_by: PolymarketOrderByEnum = PolymarketOrderByEnum.VOLUME_24HR,
) -> list[PolymarketGammaResponseDataItem]:
    """
    Binary markets have len(model.markets) == 1.
    Categorical markets have len(model.markets) > 1
    """
    client: httpx.Client = HttpxCachedClient(ttl=timedelta(seconds=60)).get_client()
    all_markets: list[PolymarketGammaResponseDataItem] = []
    offset = 0
    remaining = limit

    while remaining > 0:
        # Calculate how many items to request in this batch (up to MARKETS_LIMIT or remaining)
        # By default we fetch many markets because not possible to filter by binary/categorical
        batch_size = MARKETS_LIMIT

        # Build query parameters, excluding None values
        params = {
            "limit": batch_size,
            "active": str(active).lower() if active is not None else None,
            "archived": str(archived).lower(),
            "closed": str(closed).lower() if closed is not None else None,
            "order": order_by.value,
            "ascending": str(ascending).lower(),
            "offset": offset,
        }
        params_not_none = {k: v for k, v in params.items() if v is not None}
        url = urljoin(
            POLYMARKET_GAMMA_API_BASE_URL,
            f"events/pagination",
        )

        r = client.get(url, params=params_not_none)
        r.raise_for_status()

        market_response = response_to_model(r, PolymarketGammaResponse)

        markets_to_add = []
        for m in market_response.data:
            # Some Polymarket markets are missing the markets field
            if m.markets is None:
                continue
            if excluded_questions and m.title in excluded_questions:
                continue

            sorted_outcome_list = sorted(m.markets[0].outcomes_list)
            if only_binary:
                # We keep markets that are only Yes,No
                if len(m.markets) > 1 or sorted_outcome_list != [
                    POLYMARKET_FALSE_OUTCOME,
                    POLYMARKET_TRUE_OUTCOME,
                ]:
                    continue

            if not m.startDate or (created_after and created_after > m.startDate):
                continue

            markets_to_add.append(m)

        if only_binary:
            markets_to_add = [
                market
                for market in markets_to_add
                if market.markets is not None and len(market.markets) == 1
            ]

        # Add the markets from this batch to our results
        all_markets.extend(markets_to_add)

        # Update counters
        offset += len(market_response.data)
        remaining -= len(markets_to_add)

        # Stop if we've reached our limit or there are no more results
        if (
            remaining <= 0
            or not market_response.pagination.hasMore
            or len(market_response.data) == 0
        ):
            break

    # Return exactly the number of items requested (in case we got more due to batch size)
    return all_markets[:limit]


@tenacity.retry(
    stop=tenacity.stop_after_attempt(2),
    wait=tenacity.wait_fixed(1),
    after=lambda x: logger.debug(
        f"get_user_positions failed, attempt={x.attempt_number}."
    ),
)
def get_user_positions(
    user_id: ChecksumAddress,
    condition_ids: list[HexBytes] | None = None,
) -> list[PolymarketPositionResponse]:
    """Fetch a user's Polymarket positions; optionally filter by condition IDs."""
    url = "https://data-api.polymarket.com/positions"
    # ... rest of implementation ...
    client: httpx.Client = HttpxCachedClient(ttl=timedelta(seconds=60)).get_client()

    params = {
        "user": user_id,
        "market": ",".join([i.to_0x_hex() for i in condition_ids])
        if condition_ids
        else None,
        "sortBy": "CASHPNL",  # Available options: TOKENS, CURRENT, INITIAL, CASHPNL, PERCENTPNL, TITLE, RESOLVING, PRICE
    }
    params = {k: v for k, v in params.items() if v is not None}

    response = client.get(url, params=params)
    response.raise_for_status()
    data = response.json()
    items = [PolymarketPositionResponse.model_validate(d) for d in data]
    return items
