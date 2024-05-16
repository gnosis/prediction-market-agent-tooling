import typing as t

import requests
import tenacity
from loguru import logger

from prediction_market_agent_tooling.markets.polymarket.data_models import (
    POLYMARKET_FALSE_OUTCOME,
    POLYMARKET_TRUE_OUTCOME,
    MarketsEndpointResponse,
    PolymarketMarket,
    PolymarketMarketWithPrices,
    PolymarketPriceResponse,
    PolymarketTokenWithPrices,
    Prices,
)
from prediction_market_agent_tooling.tools.utils import response_to_model

POLYMARKET_API_BASE_URL = "https://clob.polymarket.com/"
MARKETS_LIMIT = 100  # Polymarket will only return up to 100 markets


@tenacity.retry(
    stop=tenacity.stop_after_attempt(3),
    wait=tenacity.wait_chain(*[tenacity.wait_fixed(n) for n in range(1, 4)]),
    after=lambda x: logger.debug(f"get_polymarkets failed, {x.attempt_number=}."),
)
def get_polymarkets(
    limit: int,
    with_rewards: bool = False,
    next_cursor: str | None = None,
) -> MarketsEndpointResponse:
    url = (
        f"{POLYMARKET_API_BASE_URL}/{'sampling-markets' if with_rewards else 'markets'}"
    )
    params: dict[str, str | int | float | None] = {
        "limit": min(limit, MARKETS_LIMIT),
    }
    if next_cursor is not None:
        params["next_cursor"] = next_cursor
    return response_to_model(requests.get(url, params=params), MarketsEndpointResponse)


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
            if main_markets_only and not market.fetch_if_its_a_main_market():
                continue

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
    url = f"{POLYMARKET_API_BASE_URL}/markets/{condition_id}"
    return response_to_model(requests.get(url), PolymarketMarket)


def get_token_price(
    token_id: str, side: t.Literal["buy", "sell"]
) -> PolymarketPriceResponse:
    url = f"{POLYMARKET_API_BASE_URL}/price"
    params = {"token_id": token_id, "side": side}
    return response_to_model(requests.get(url, params=params), PolymarketPriceResponse)


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
