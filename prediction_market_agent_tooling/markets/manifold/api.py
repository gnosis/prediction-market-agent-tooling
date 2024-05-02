import typing as t
from datetime import datetime

import requests
import tenacity

from prediction_market_agent_tooling.gtypes import Mana, SecretStr
from prediction_market_agent_tooling.loggers.loggers import logger
from prediction_market_agent_tooling.markets.data_models import (
    BetAmount,
    Currency,
    ResolvedBet,
)
from prediction_market_agent_tooling.markets.manifold.data_models import (
    ManifoldBet,
    ManifoldContractMetric,
    ManifoldMarket,
    ManifoldUser,
)
from prediction_market_agent_tooling.tools.parallelism import par_map
from prediction_market_agent_tooling.tools.utils import response_list_to_model

"""
Python API for Manifold Markets

https://docs.manifold.markets/api#get-v0search-markets

Note: There is an existing wrapper here: https://github.com/vluzko/manifoldpy. Consider using that instead.
"""

MANIFOLD_API_BASE_URL = "https://api.manifold.markets"
MARKETS_LIMIT = 1000  # Manifold will only return up to 1000 markets


def get_manifold_binary_markets(
    limit: int,
    term: str = "",
    topic_slug: t.Optional[str] = None,
    sort: t.Literal["liquidity", "score", "newest", "close-date"] | None = "liquidity",
    filter_: (
        t.Literal[
            "open", "closed", "resolved", "closing-this-month", "closing-next-month"
        ]
        | None
    ) = "open",
    created_after: t.Optional[datetime] = None,
    excluded_questions: set[str] | None = None,
) -> list[ManifoldMarket]:
    all_markets: list[ManifoldMarket] = []

    url = f"{MANIFOLD_API_BASE_URL}/v0/search-markets"
    params: dict[str, t.Union[str, int, float]] = {
        "term": term,
        "limit": min(limit, MARKETS_LIMIT),
        "contractType": "BINARY",
    }
    if sort:
        params["sort"] = sort
    if filter_:
        params["filter"] = filter_
    if topic_slug:
        params["topicSlug"] = topic_slug

    offset = 0
    while True:
        params["offset"] = offset
        response = requests.get(url, params=params)
        response.raise_for_status()
        data = response.json()
        markets = [ManifoldMarket.model_validate(x) for x in data]

        if not markets:
            break

        found_all_new_markets = False
        for market in markets:
            if created_after and market.createdTime < created_after:
                if sort == "newest":
                    found_all_new_markets = True
                    break
                else:
                    continue

            if excluded_questions and market.question in excluded_questions:
                continue

            all_markets.append(market)

        if found_all_new_markets:
            break

        if len(all_markets) >= limit:
            break

        offset += len(markets)

    return all_markets[:limit]


def get_one_manifold_binary_market() -> ManifoldMarket:
    return get_manifold_binary_markets(1)[0]


@tenacity.retry(
    stop=tenacity.stop_after_attempt(3),
    wait=tenacity.wait_fixed(1),
    after=lambda x: logger.debug(f"place_bet failed, {x.attempt_number=}."),
)
def place_bet(
    amount: Mana, market_id: str, outcome: bool, manifold_api_key: SecretStr
) -> None:
    outcome_str = "YES" if outcome else "NO"
    url = f"{MANIFOLD_API_BASE_URL}/v0/bet"
    params = {
        "amount": float(amount),  # Convert to float to avoid serialization issues.
        "contractId": market_id,
        "outcome": outcome_str,
    }

    headers = {
        "Authorization": f"Key {manifold_api_key.get_secret_value()}",
        "Content-Type": "application/json",
    }
    response = requests.post(url, json=params, headers=headers)

    if response.status_code == 200:
        data = response.json()
        if not data["isFilled"]:
            raise RuntimeError(
                f"Placing bet failed: {response.status_code} {response.reason} {response.text}"
            )
    else:
        raise Exception(
            f"Placing bet failed: {response.status_code} {response.reason} {response.text}"
        )


def get_authenticated_user(api_key: str) -> ManifoldUser:
    url = f"{MANIFOLD_API_BASE_URL}/v0/me"
    headers = {
        "Authorization": f"Key {api_key}",
        "Content-Type": "application/json",
        "Cache-Control": "private, no-store, max-age=0",
    }
    response = requests.get(url, headers=headers)
    response.raise_for_status()
    return ManifoldUser.model_validate(response.json())


@tenacity.retry(
    stop=tenacity.stop_after_attempt(3),
    wait=tenacity.wait_fixed(1),
    after=lambda x: logger.debug(f"get_manifold_market failed, {x.attempt_number=}."),
)
def get_manifold_market(market_id: str) -> ManifoldMarket:
    url = f"{MANIFOLD_API_BASE_URL}/v0/market/{market_id}"
    response = requests.get(url)
    response.raise_for_status()
    return ManifoldMarket.model_validate(response.json())


@tenacity.retry(
    stop=tenacity.stop_after_attempt(3),
    wait=tenacity.wait_fixed(1),
    after=lambda x: logger.debug(f"get_manifold_bets failed, {x.attempt_number=}."),
)
def get_manifold_bets(
    user_id: str,
    start_time: datetime,
    end_time: t.Optional[datetime],
) -> list[ManifoldBet]:
    url = f"{MANIFOLD_API_BASE_URL}/v0/bets"

    params: dict[str, str] = {"userId": user_id}
    bets = response_list_to_model(requests.get(url, params=params), ManifoldBet)
    bets = [b for b in bets if b.createdTime >= start_time]
    if end_time:
        bets = [b for b in bets if b.createdTime < end_time]
    return bets


def get_resolved_manifold_bets(
    user_id: str,
    start_time: datetime,
    end_time: t.Optional[datetime],
) -> tuple[list[ManifoldBet], list[ManifoldMarket]]:
    bets = get_manifold_bets(user_id, start_time, end_time)
    markets: list[ManifoldMarket] = par_map(
        items=bets,
        func=lambda bet: get_manifold_market(bet.contractId),
    )
    resolved_markets, resolved_bets = [], []
    for bet, market in zip(bets, markets):
        if market.is_resolved_non_cancelled():
            resolved_markets.append(market)
            resolved_bets.append(bet)
    return resolved_bets, resolved_markets


def manifold_to_generic_resolved_bet(
    bet: ManifoldBet, market: ManifoldMarket
) -> ResolvedBet:
    if market.id != bet.contractId:
        raise ValueError(f"Bet {bet.contractId} and market {market.id} do not match.")
    if not market.is_resolved_non_cancelled():
        raise ValueError(f"Market {market.id} is not resolved.")
    if not market.resolutionTime:
        raise ValueError(f"Market {market.id} has no resolution time.")

    market_outcome = market.get_resolved_boolean_outcome()
    return ResolvedBet(
        amount=BetAmount(amount=bet.amount, currency=Currency.Mana),
        outcome=bet.get_resolved_boolean_outcome(),
        created_time=bet.createdTime,
        market_question=market.question,
        market_outcome=market_outcome,
        resolved_time=market.resolutionTime,
        profit=bet.get_profit(market_outcome=market_outcome),
    )


def get_market_positions(market_id: str, user_id: str) -> list[ManifoldContractMetric]:
    url = f"{MANIFOLD_API_BASE_URL}/v0/market/{market_id}/positions"
    params = {"userId": user_id}
    response = requests.get(url, params=params)
    response.raise_for_status()
    return [ManifoldContractMetric.model_validate(x) for x in response.json()]
