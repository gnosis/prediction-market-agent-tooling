import json
import typing as t
from datetime import datetime
from enum import Enum

import pytz
import requests
from pydantic import BaseModel, validator

MANIFOLD_API_LIMIT = 1000  # Manifold will only return up to 1000 markets


class EvaluatedQuestion(BaseModel):
    question: str
    is_predictable: bool


class MarketSource(str, Enum):
    MANIFOLD = "manifold"
    POLYMARKET = "polymarket"


class Market(BaseModel):
    source: MarketSource
    question: str
    url: str
    p_yes: float
    volume: float
    is_resolved: bool
    created_time: datetime
    resolution: str | None = None
    outcomePrices: list[float] | None = None

    @validator("outcomePrices", pre=True)
    def _validate_outcome_prices(cls, value: list[float] | None) -> list[float] | None:
        if value is None:
            return None
        if len(value) != 2:
            raise ValueError("outcomePrices must have exactly 2 elements.")
        return value

    @validator("created_time")
    def _validate_created_time(cls, value: datetime) -> datetime:
        if value.tzinfo is None:
            value = value.replace(tzinfo=pytz.UTC)
        return value

    @property
    def p_no(self) -> float:
        return 1 - self.p_yes

    @property
    def yes_outcome_price(self) -> float:
        # Use the outcome price if available, otherwise assume it's p_yes.
        return self.outcomePrices[0] if self.outcomePrices else self.p_yes

    @property
    def no_outcome_price(self) -> float:
        # Use the outcome price if available, otherwise assume it's p_yes.
        return self.outcomePrices[1] if self.outcomePrices else 1 - self.p_yes


class OutcomePrediction(BaseModel):
    p_yes: float
    confidence: float
    info_utility: t.Optional[float]

    @property
    def binary_answer(self) -> bool:
        return self.p_yes > 0.5


class Prediction(BaseModel):
    evaluation: t.Optional[EvaluatedQuestion] = None
    outcome_prediction: t.Optional[OutcomePrediction] = None

    time: t.Optional[float] = None
    cost: t.Optional[float] = None

    @property
    def is_answered(self) -> bool:
        return self.outcome_prediction is not None


AgentPredictions = t.Dict[str, Prediction]
Predictions = t.Dict[str, AgentPredictions]


class PredictionsCache(BaseModel):
    predictions: Predictions

    def get_prediction(self, agent_name: str, question: str) -> Prediction:
        return self.predictions[agent_name][question]

    def has_market(self, agent_name: str, question: str) -> bool:
        return (
            agent_name in self.predictions and question in self.predictions[agent_name]
        )

    def add_prediction(
        self, agent_name: str, question: str, prediction: Prediction
    ) -> None:
        if agent_name not in self.predictions:
            self.predictions[agent_name] = {}
        assert (
            question not in self.predictions[agent_name]
        ), f"Question `{question}` already exists in the cache."
        self.predictions[agent_name][question] = prediction

    def save(self, path: str) -> None:
        with open(path, "w") as f:
            json.dump(self.dict(), f, indent=2)

    @staticmethod
    def load(path: str) -> "PredictionsCache":
        with open(path, "r") as f:
            return PredictionsCache.model_validate(json.load(f))


def get_manifold_markets(
    limit: int = 100,
    offset: int = 0,
    filter_: t.Literal[
        "open", "closed", "resolved", "closing-this-month", "closing-next-month"
    ] = "open",
    sort: t.Literal["liquidity", "score", "newest"] = "liquidity",
) -> t.List[Market]:
    url = "https://api.manifold.markets/v0/search-markets"
    params = {
        "term": "",
        "sort": sort,
        "filter": filter_,
        "limit": f"{limit}",
        "offset": offset,
        "contractType": "BINARY",  # TODO support CATEGORICAL markets
    }
    response = requests.get(url, params=params)

    response.raise_for_status()
    markets_json = response.json()
    for m in markets_json:
        m["source"] = MarketSource.MANIFOLD

    # Map JSON fields to Market fields
    fields_map = {
        "probability": "p_yes",
        "isResolved": "is_resolved",
        "createdTime": "created_time",
    }

    def _map_fields(old: dict[str, str], mapping: dict[str, str]) -> dict[str, str]:
        return {mapping.get(k, k): v for k, v in old.items()}

    markets = [Market.model_validate(_map_fields(m, fields_map)) for m in markets_json]

    return markets


def get_manifold_markets_paged(
    number: int = 100,
    filter_: t.Literal[
        "open", "closed", "resolved", "closing-this-month", "closing-next-month"
    ] = "open",
    sort: t.Literal["liquidity", "score", "newest"] = "liquidity",
    starting_offset: int = 0,
    excluded_questions: set[str] | None = None,
) -> t.List[Market]:
    markets: list[Market] = []

    offset = starting_offset
    while len(markets) < number:
        new_markets = get_manifold_markets(
            limit=min(MANIFOLD_API_LIMIT, number - len(markets)),
            offset=offset,
            filter_=filter_,
            sort=sort,
        )
        if not new_markets:
            break
        markets.extend(
            market
            for market in new_markets
            if not excluded_questions or market.question not in excluded_questions
        )
        offset += len(new_markets)

    return markets


def get_manifold_markets_dated(
    oldest_date: datetime,
    filter_: t.Literal[
        "open", "closed", "resolved", "closing-this-month", "closing-next-month"
    ] = "open",
    excluded_questions: set[str] | None = None,
) -> t.List[Market]:
    markets: list[Market] = []

    offset = 0
    while True:
        new_markets = get_manifold_markets(
            limit=MANIFOLD_API_LIMIT,
            offset=offset,
            filter_=filter_,
            sort="newest",  # Enforce sorting by newest, because there aren't date filters on the API.
        )
        if not new_markets:
            break
        for market in new_markets:
            if market.created_time < oldest_date:
                return markets
            if not excluded_questions or market.question not in excluded_questions:
                markets.append(market)
            offset += 1

    return markets


def get_polymarket_markets(
    limit: int = 100,
    active: bool | None = True,
    closed: bool | None = False,
    excluded_questions: set[str] | None = None,
) -> t.List[Market]:
    params: dict[str, str | int] = {
        "_limit": limit,
    }
    if active is not None:
        params["active"] = "true" if active else "false"
    if closed is not None:
        params["closed"] = "true" if closed else "false"
    api_uri = f"https://strapi-matic.poly.market/markets"
    ms_json = requests.get(api_uri, params=params).json()
    markets: t.List[Market] = []
    for m_json in ms_json:
        # Skip non-binary markets. Unfortunately no way to filter in the API call
        # TODO support CATEGORICAL markets
        if m_json["outcomes"] != ["Yes", "No"]:
            continue

        if excluded_questions and m_json["question"] in excluded_questions:
            continue

        markets.append(
            Market(
                question=m_json["question"],
                url=f"https://polymarket.com/event/{m_json['slug']}",
                p_yes=m_json["outcomePrices"][
                    0
                ],  # For binary markets on Polymarket, the first outcome is "Yes" and outcomePrices are equal to probabilities.
                created_time=m_json["created_at"],
                outcomePrices=m_json["outcomePrices"],
                volume=m_json["volume"],
                is_resolved=False,
                source=MarketSource.POLYMARKET,
            )
        )
    return markets


def get_markets(
    number: int,
    source: MarketSource,
) -> t.List[Market]:
    if source == MarketSource.MANIFOLD:
        return get_manifold_markets(limit=number)
    elif source == MarketSource.POLYMARKET:
        return get_polymarket_markets(limit=number)
    else:
        raise ValueError(f"Unknown market source: {source}")


def get_llm_api_call_cost(
    model: str, prompt_tokens: int, completion_tokens: float
) -> float:
    """
    In older versions of langchain, the cost calculation doesn't work for
    newer models. This is a temporary workaround to get the cost.

    See:
    https://github.com/langchain-ai/langchain/issues/12994

    Costs are in USD, per 1000 tokens.
    """
    model_costs = {
        "gpt-4-1106-preview": {
            "prompt_tokens": 0.01,
            "completion_tokens": 0.03,
        },
        "gpt-3.5-turbo-0125": {
            "prompt_tokens": 0.0005,
            "completion_tokens": 0.0015,
        },
    }
    if model not in model_costs:
        raise ValueError(f"Unknown model: {model}")

    model_cost = model_costs[model]["prompt_tokens"] * prompt_tokens
    model_cost += model_costs[model]["completion_tokens"] * completion_tokens
    model_cost /= 1000
    return model_cost


def should_not_happen(message: str, E: t.Type[Exception] = RuntimeError) -> t.NoReturn:
    raise E(message)
