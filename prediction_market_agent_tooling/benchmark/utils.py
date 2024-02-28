import json
import typing as t
from datetime import datetime
from enum import Enum

import pytz
import requests
from pydantic import BaseModel, validator

from prediction_market_agent_tooling.tools.utils import should_not_happen

MANIFOLD_API_LIMIT = 1000  # Manifold will only return up to 1000 markets


class MarketSource(str, Enum):
    MANIFOLD = "manifold"
    POLYMARKET = "polymarket"


class MarketFilter(str, Enum):
    open = "open"
    resolved = "resolved"
    closing_this_month = "closing-this-month"


class MarketSort(str, Enum):
    liquidity = "liquidity"
    newest = "newest"


class MarketResolution(str, Enum):
    YES = "yes"
    NO = "no"


class CancelableMarketResolution(str, Enum):
    YES = "yes"
    NO = "no"
    CANCEL = "cancel"
    MKT = "mkt"


class Market(BaseModel):
    source: MarketSource
    question: str
    category: str | None = None
    url: str
    p_yes: float
    volume: float
    created_time: datetime
    close_time: datetime
    resolution: CancelableMarketResolution | None = None
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

    @validator("close_time")
    def _validate_close_time(cls, value: datetime) -> datetime:
        if value.tzinfo is None:
            value = value.replace(tzinfo=pytz.UTC)
        return value

    @property
    def is_resolved(self) -> bool:
        return self.resolution is not None

    @property
    def has_unsuccessful_resolution(self) -> bool:
        return self.resolution in [
            CancelableMarketResolution.CANCEL,
            CancelableMarketResolution.MKT,
        ]

    @property
    def has_successful_resolution(self) -> bool:
        return self.is_resolved and not self.has_unsuccessful_resolution

    @property
    def is_cancelled(self) -> bool:
        return self.resolution == CancelableMarketResolution.CANCEL

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
            MarketResolution.YES
            if (
                (
                    self.resolution is not None
                    and self.resolution == CancelableMarketResolution.YES
                )
                or (self.resolution is None and self.p_yes > 0.5)
            )
            else (
                MarketResolution.NO
                if (
                    (
                        self.resolution is not None
                        and self.resolution == CancelableMarketResolution.NO
                    )
                    or (self.resolution is None and self.p_yes <= 0.5)
                )
                else should_not_happen(
                    f"Unknown resolution `{self.resolution}`, if it is `cancel`, you should first filter out cancelled markets."
                )
            )
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
        "createdTime": "created_time",
        "closeTime": "close_time",
    }
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
        Market.model_validate(_map_fields(m, fields_map, process_values))
        for m in markets_json
    ]

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

        resolution = (
            CancelableMarketResolution.YES
            if closed and m_json["outcomePrices"][0] == "1.0"
            else (
                CancelableMarketResolution.NO
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
                category=m_json["category"],
                url=f"https://polymarket.com/event/{m_json['slug']}",
                p_yes=m_json["outcomePrices"][
                    0
                ],  # For binary markets on Polymarket, the first outcome is "Yes" and outcomePrices are equal to probabilities.
                created_time=m_json["created_at"],
                close_time=datetime.strptime(m_json["end_date_iso"], "%Y-%m-%d"),
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
    filter_: MarketFilter = MarketFilter.open,
    sort: MarketSort | None = None,
    excluded_questions: set[str] | None = None,
) -> t.List[Market]:
    if source == MarketSource.MANIFOLD:
        return get_manifold_markets_paged(
            number=number,
            excluded_questions=excluded_questions,
            filter_=filter_.value,
            sort=(sort or MarketSort.liquidity).value,
        )
    elif source == MarketSource.POLYMARKET:
        if sort is not None:
            raise ValueError(f"Polymarket doesn't support sorting.")
        if filter_ == MarketFilter.closing_this_month:
            raise ValueError(f"Polymarket doesn't support filtering by closing soon.")
        return get_polymarket_markets(
            limit=number,
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
