import typing as t
from urllib.parse import urljoin

import tenacity

from prediction_market_agent_tooling.loggers import logger
from prediction_market_agent_tooling.markets.polymarket.data_models import (
    POLYMARKET_FALSE_OUTCOME,
    POLYMARKET_TRUE_OUTCOME,
    MarketsEndpointResponse,
    PolymarketMarket,
    PolymarketMarketWithPrices,
    PolymarketPriceResponse,
    PolymarketTokenWithPrices,
    Prices,
    PolymarketGammaResponse,
    PolymarketGammaResponseDataItem,
)
from prediction_market_agent_tooling.tools.httpx_cached_client import HttpxCachedClient
from prediction_market_agent_tooling.tools.utils import response_to_model, utcnow

POLYMARKET_API_BASE_URL = "https://clob.polymarket.com/"
MARKETS_LIMIT = 10  # Polymarket will only return up to 100 markets
POLYMARKET_GAMMA_API_BASE_URL = "https://gamma-api.polymarket.com/"


def get_polymarkets_markets(
    limit: int,
    active: bool = True,
    archived: bool = False,
    closed: bool = False,
    ascending: bool = False,
) -> list[PolymarketGammaResponseDataItem]:
    client = HttpxCachedClient().get_client()
    all_markets: list[PolymarketGammaResponseDataItem] = []
    offset = 0
    remaining = limit

    while remaining > 0:
        # Calculate how many items to request in this batch (up to MARKETS_LIMIT or remaining)
        batch_size = min(remaining, MARKETS_LIMIT)

        url = urljoin(
            POLYMARKET_GAMMA_API_BASE_URL,
            f"events/pagination?limit={batch_size}&active={str(active).lower()}&archived={str(archived).lower()}&closed={str(closed).lower()}&order=volume24hr&ascending={str(ascending).lower()}&offset={offset}",
        )

        r = client.get(url)
        market_response = response_to_model(r, PolymarketGammaResponse)

        # Add the markets from this batch to our results
        all_markets.extend(market_response.data)

        # Update counters
        received = len(market_response.data)
        offset += received
        remaining -= received

        # Stop if we've reached our limit or there are no more results
        if remaining <= 0 or not market_response.pagination.hasMore or received == 0:
            break

    # Return exactly the number of items requested (in case we got more due to batch size)
    return all_markets[:limit]


@tenacity.retry(
    stop=tenacity.stop_after_attempt(2),
    wait=tenacity.wait_fixed(1),
    after=lambda x: logger.debug(f"get_polymarkets failed, {x.attempt_number=}."),
)
def get_polymarkets(
    limit: int,
    with_rewards: bool = False,
    next_cursor: str | None = None,
) -> MarketsEndpointResponse:
    url = urljoin(
        POLYMARKET_API_BASE_URL, "sampling-markets" if with_rewards else "markets"
    )
    params: dict[str, str | int | float | None] = {
        "limit": min(limit, MARKETS_LIMIT),
    }
    if next_cursor is not None:
        params["next_cursor"] = next_cursor
    cached_client = HttpxCachedClient().get_client()
    data = cached_client.get(url, params=params)
    return response_to_model(data, MarketsEndpointResponse)


def get_polymarket_binary_markets(
    limit: int,
    closed: bool | None = False,
    excluded_questions: set[str] | None = None,
    with_rewards: bool = False,
    main_markets_only: bool = True,
) -> list[PolymarketMarketWithPrices]:
    """
    See https://learn.polymarket.com/trading-rewards for information about rewards.
    """

    all_markets: list[PolymarketMarketWithPrices] = []
    next_cursor: str | None = None

    while True:
        print(f"fetching markets... {utcnow()}")
        response = get_polymarkets(
            limit, with_rewards=with_rewards, next_cursor=next_cursor
        )

        for market in response.data:
            # Closed markets means resolved markets.
            if closed is not None and market.closed != closed:
                continue

            # Skip markets that are inactive.
            # Documentation does not provide more details about this, but if API returns them, website gives "Oops...we didn't forecast this".
            if not market.active:
                continue

            # Skip also those that were archived.
            # Again nothing about it in documentation and API doesn't seem to return them, but to be safe.
            if market.archived:
                continue

            if excluded_questions and market.question in excluded_questions:
                continue

            # Atm we work with binary markets only.
            if sorted(token.outcome for token in market.tokens) != [
                POLYMARKET_FALSE_OUTCOME,
                POLYMARKET_TRUE_OUTCOME,
            ]:
                continue

            # This is pretty slow to do here, but our safest option at the moment. So keep it as the last filter.
            # TODO: Add support for `description` for `AgentMarket` and if it isn't None, use it in addition to the question in all agents. Then this can be removed.
            # ToDo - investigate
            # if main_markets_only and not market.fetch_if_its_a_main_market():
            #    continue

            tokens_with_price = get_market_tokens_with_prices(market)
            market_with_prices = PolymarketMarketWithPrices.model_validate(
                {**market.model_dump(), "tokens": tokens_with_price}
            )

            all_markets.append(market_with_prices)

        if len(all_markets) >= limit:
            break

        next_cursor = response.next_cursor

        if next_cursor == "LTE=":
            # 'LTE=' means the end.
            break

    return all_markets[:limit]


def get_polymarket_market(condition_id: str) -> PolymarketMarket:
    url = urljoin(POLYMARKET_API_BASE_URL, f"markets/{condition_id}")
    client = HttpxCachedClient().get_client()
    return response_to_model(client.get(url), PolymarketMarket)


def get_token_price(
    token_id: str, side: t.Literal["buy", "sell"]
) -> PolymarketPriceResponse:
    url = urljoin(POLYMARKET_API_BASE_URL, "price")
    params = {"token_id": token_id, "side": side}
    client = HttpxCachedClient().get_client()
    return response_to_model(client.get(url, params=params), PolymarketPriceResponse)


def get_market_tokens_with_prices(
    market: PolymarketMarket,
) -> list[PolymarketTokenWithPrices]:
    tokens_with_prices = [
        PolymarketTokenWithPrices(
            token_id=token.token_id,
            outcome=token.outcome,
            winner=token.winner,
            prices=Prices(
                BUY=get_token_price(token.token_id, "buy").price_dec,
                SELL=get_token_price(token.token_id, "sell").price_dec,
            ),
        )
        for token in market.tokens
    ]
    return tokens_with_prices
