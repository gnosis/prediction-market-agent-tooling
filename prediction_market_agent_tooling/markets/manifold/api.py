import typing as t
from datetime import datetime

import requests

from prediction_market_agent_tooling.config import APIKeys
from prediction_market_agent_tooling.gtypes import Mana
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
    sort: t.Literal["liquidity", "score", "newest", "close-date"] = "liquidity",
    filter_: t.Literal[
        "open", "closed", "resolved", "closing-this-month", "closing-next-month"
    ] = "open",
    created_after: t.Optional[datetime] = None,
) -> list[ManifoldMarket]:
    all_markets: list[ManifoldMarket] = []

    url = f"{MANIFOLD_API_BASE_URL}/v0/search-markets"
    params: dict[str, t.Union[str, int, float]] = {
        "term": term,
        "sort": sort,
        "filter": filter_,
        "limit": min(limit, MARKETS_LIMIT),
        "contractType": "BINARY",
    }
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

        for market in markets:
            if created_after and market.createdTime < created_after:
                if sort == "newest":
                    break
                else:
                    continue
            all_markets.append(market)

        if len(all_markets) >= limit:
            break

        offset += len(markets)

    return all_markets[:limit]


def get_one_manifold_binary_market() -> ManifoldMarket:
    return get_manifold_binary_markets(1)[0]


def place_bet(amount: Mana, market_id: str, outcome: bool) -> None:
    outcome_str = "YES" if outcome else "NO"
    url = f"{MANIFOLD_API_BASE_URL}/v0/bet"
    params = {
        "amount": float(amount),  # Convert to float to avoid serialization issues.
        "contractId": market_id,
        "outcome": outcome_str,
    }

    headers = {
        "Authorization": f"Key {APIKeys().manifold_api_key.get_secret_value()}",
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
    }
    response = requests.get(url, headers=headers)
    response.raise_for_status()
    return ManifoldUser.model_validate(response.json())


def get_manifold_market(market_id: str) -> ManifoldMarket:
    url = f"{MANIFOLD_API_BASE_URL}/v0/market/{market_id}"
    response = requests.get(url)
    response.raise_for_status()
    return ManifoldMarket.model_validate(response.json())


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
) -> list[ManifoldBet]:
    bets = get_manifold_bets(user_id, start_time, end_time)
    bets = [
        b for b in bets if get_manifold_market(b.contractId).is_resolved_non_cancelled()
    ]
    return bets


def manifold_to_generic_resolved_bet(bet: ManifoldBet) -> ResolvedBet:
    market = get_manifold_market(bet.contractId)
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
