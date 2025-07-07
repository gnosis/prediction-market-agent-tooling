import typing as t
from enum import Enum
from urllib.parse import urljoin

import httpx
import tenacity

from prediction_market_agent_tooling.loggers import logger
from prediction_market_agent_tooling.markets.polymarket.data_models import (
    POLYMARKET_FALSE_OUTCOME,
    POLYMARKET_TRUE_OUTCOME,
    PolymarketGammaResponse,
    PolymarketGammaResponseDataItem,
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
    client: httpx.Client = HttpxCachedClient(ttl=60).get_client()
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
        query_string = "&".join(f"{k}={v}" for k, v in params.items() if v is not None)
        url = urljoin(
            POLYMARKET_GAMMA_API_BASE_URL,
            f"events/pagination?{query_string}",
        )

        r = client.get(url)

        market_response = response_to_model(r, PolymarketGammaResponse)

        markets_to_add = []
        for m in market_response.data:
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

            if created_after and created_after > m.startDate:
                continue

            markets_to_add.append(m)

        if only_binary:
            markets_to_add = [
                market for market in market_response.data if len(market.markets) == 1
            ]

        # Add the markets from this batch to our results
        all_markets.extend(markets_to_add)

        # Update counters
        received = len(market_response.data)
        offset += received
        remaining -= received

        # Stop if we've reached our limit or there are no more results
        if remaining <= 0 or not market_response.pagination.hasMore or received == 0:
            break

    # Return exactly the number of items requested (in case we got more due to batch size)
    return all_markets[:limit]
