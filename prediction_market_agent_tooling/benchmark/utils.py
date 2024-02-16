import json
import typing as t
from datetime import datetime
from enum import Enum

import pytz
import requests
from pydantic import BaseModel, validator

from prediction_market_agent_tooling.tools.utils import should_not_happen


class MarketSource(str, Enum):
    MANIFOLD = "manifold"
    POLYMARKET = "polymarket"


class MarketFilter(str, Enum):
    open = "open"
    resolved = "resolved"


class MarketResolution(str, Enum):
    YES = "yes"
    NO = "no"


class Market(BaseModel):
    source: MarketSource
    question: str
    url: str
    p_yes: float
    volume: float
    created_time: datetime
    resolution: MarketResolution | None = None
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
    def is_resolved(self) -> bool:
        return self.resolution is not None

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

    @property
    def probable_resolution(self) -> MarketResolution:
        return (
            self.resolution
            if self.resolution is not None
            else MarketResolution.YES
            if self.p_yes > 0.5
            else MarketResolution.NO
        )


class OutcomePrediction(BaseModel):
    p_yes: float
    confidence: float
    info_utility: t.Optional[float]

    @property
    def probable_resolution(self) -> MarketResolution:
        return MarketResolution.YES if self.p_yes > 0.5 else MarketResolution.NO


class Prediction(BaseModel):
    is_predictable: bool = True
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
            return PredictionsCache.parse_obj(json.load(f))


def get_manifold_markets(
    number: int = 100,
    excluded_questions: t.List[str] = [],
    filter_: t.Literal[
        "open", "closed", "resolved", "closing-this-month", "closing-next-month"
    ] = "open",
) -> t.List[Market]:
    url = "https://api.manifold.markets/v0/search-markets"
    params = {
        "term": "",
        "sort": "liquidity",
        "filter": filter_,
        "limit": f"{number + len(excluded_questions)}",
        "contractType": "BINARY",  # TODO support CATEGORICAL markets
    }
    response = requests.get(url, params=params)

    response.raise_for_status()
    markets_json = response.json()
    for m in markets_json:
        m["source"] = MarketSource.MANIFOLD

    # Map JSON fields to Market fields
    fields_map = {"probability": "p_yes", "createdTime": "created_time"}
    process_values = {
        "resolution": lambda v: v.lower() if v else None,
    }

    def _map_fields(
        old: dict[str, str],
        mapping: dict[str, str],
        processing: dict[str, t.Callable[[t.Any], t.Any]],
    ) -> dict[str, str]:
        return {
            mapping.get(k, k): processing.get(k, lambda x: x)(v) for k, v in old.items()
        }

    markets = [
        Market.parse_obj(_map_fields(m, fields_map, process_values))
        for m in markets_json
    ]

    # Filter out markets with excluded questions
    markets = [m for m in markets if m.question not in excluded_questions]

    return markets[:number]


def get_polymarket_markets(
    number: int = 100,
    excluded_questions: t.List[str] = [],
    active: bool | None = True,
    closed: bool | None = False,
) -> t.List[Market]:
    params: dict[str, str | int] = {
        "_limit": number + len(excluded_questions),
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

        if m_json["question"] in excluded_questions:
            print(f"Skipping market with 'excluded question': {m_json['question']}")
            continue

        resolution = (
            MarketResolution.YES
            if closed and m_json["outcomePrices"][0] == "1.0"
            else (
                MarketResolution.NO
                if closed and m_json["outcomePrices"][1] == "1.0"
                else (
                    should_not_happen()
                    if closed
                    and m_json["outcomePrices"] not in (["1.0", "0.0"], ["0.0", "1.0"])
                    else None
                )
            )
        )

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
                resolution=resolution,
                source=MarketSource.POLYMARKET,
            )
        )
    return markets


def get_markets(
    number: int,
    source: MarketSource,
    excluded_questions: t.List[str] = [],
    filter_: MarketFilter = MarketFilter.open,
) -> t.List[Market]:
    if source == MarketSource.MANIFOLD:
        return get_manifold_markets(
            number=number, excluded_questions=excluded_questions, filter_=filter_.value
        )
    elif source == MarketSource.POLYMARKET:
        return get_polymarket_markets(
            number=number,
            excluded_questions=excluded_questions,
            closed=(
                True
                if filter_ == MarketFilter.resolved
                else (
                    False
                    if filter_ == MarketFilter.open
                    else should_not_happen(f"Unknown filter {filter_} for polymarket.")
                )
            ),
        )
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
