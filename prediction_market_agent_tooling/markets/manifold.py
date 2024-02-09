import requests
import typing as t
from prediction_market_agent_tooling.gtypes import Mana
from prediction_market_agent_tooling.config import APIKeys
from prediction_market_agent_tooling.markets.data_models import (
    ManifoldMarket,
)

"""
Python API for Manifold Markets

https://docs.manifold.markets/api#get-v0search-markets

Note: There is an existing wrapper here: https://github.com/vluzko/manifoldpy. Consider using that instead.
"""


def get_manifold_binary_markets(
    limit: int,
    term: str = "",
    topic_slug: t.Optional[str] = None,
    sort: str = "liquidity",
) -> list[ManifoldMarket]:
    url = "https://api.manifold.markets/v0/search-markets"
    params: dict[str, t.Union[str, int, float]] = {
        "term": term,
        "sort": sort,
        "limit": limit,
        "filter": "open",
        "contractType": "BINARY",
    }
    if topic_slug:
        params["topicSlug"] = topic_slug
    response = requests.get(url, params=params)

    response.raise_for_status()
    data = response.json()

    markets = [ManifoldMarket.model_validate(x) for x in data]
    return markets


def pick_binary_market() -> ManifoldMarket:
    return get_manifold_binary_markets(1)[0]


def place_bet(amount: Mana, market_id: str, outcome: bool) -> None:
    outcome_str = "YES" if outcome else "NO"
    url = "https://api.manifold.markets/v0/bet"
    params = {
        "amount": float(amount),  # Convert to float to avoid serialization issues.
        "contractId": market_id,
        "outcome": outcome_str,
    }

    headers = {
        "Authorization": f"Key {APIKeys().manifold_api_key}",
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
