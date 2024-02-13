from datetime import datetime
import requests
import typing as t
from prediction_market_agent_tooling.gtypes import Mana
from prediction_market_agent_tooling.config import APIKeys
from prediction_market_agent_tooling.markets.data_models import (
    ProfitAmount,
    ResolvedBet,
    BetAmount,
    Currency,
    ManifoldBet,
    ManifoldMarket,
    ManifoldUser,
    ManifoldContractMetric,
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


def get_authenticated_user() -> ManifoldUser:
    url = "https://api.manifold.markets/v0/me"
    headers = {
        "Authorization": f"Key {APIKeys().manifold_api_key}",
        "Content-Type": "application/json",
    }
    response = requests.get(url, headers=headers)
    response.raise_for_status()
    return ManifoldUser.model_validate(response.json())


def get_manifold_market(market_id: str) -> ManifoldMarket:
    url = f"https://api.manifold.markets/v0/market/{market_id}"
    response = requests.get(url)
    response.raise_for_status()
    return ManifoldMarket.model_validate(response.json())


def get_resolved_manifold_bets(
    user_id: str,
    start_time: datetime,
    end_time: t.Optional[datetime],
) -> list[ManifoldBet]:
    url = "https://api.manifold.markets/v0/bets"

    params: dict[str, str] = {"userId": user_id}
    response = requests.get(url, params=params)
    response.raise_for_status()
    bets = [ManifoldBet.model_validate(x) for x in response.json()]
    bets = [b for b in bets if b.createdTime >= start_time]
    if end_time:
        bets = [b for b in bets if b.createdTime < end_time]
    bets = [b for b in bets if get_manifold_market(b.contractId).isResolved]
    return bets


def manifold_to_generic_resolved_bet(bet: ManifoldBet) -> ResolvedBet:
    market = get_manifold_market(bet.contractId)
    if not market.isResolved:
        raise ValueError(f"Market {market.id} is not resolved.")

    # Get the profit for this bet from the corresponding position
    positions = get_market_positions(market.id, bet.userId)
    bet_position = next(p for p in positions if p.contractId == bet.contractId)
    profit = bet_position.profit

    return ResolvedBet(
        amount=BetAmount(amount=bet.amount, currency=Currency.Mana),
        outcome=bet.outcome == "YES",
        created_time=bet.createdTime,
        market_question=market.question,
        market_outcome=market.resolution,
        resolved_time=market.resolutionTime,
        profit=ProfitAmount(amount=profit, currency=Currency.Mana),
    )


def get_market_positions(market_id: str, user_id: str) -> list[ManifoldContractMetric]:
    url = f"https://api.manifold.markets/v0/market/{market_id}/positions"
    params = {"userId": user_id}
    response = requests.get(url, params=params)
    response.raise_for_status()
    return [ManifoldContractMetric.model_validate(x) for x in response.json()]
