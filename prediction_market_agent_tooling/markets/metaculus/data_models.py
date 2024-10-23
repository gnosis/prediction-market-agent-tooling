from enum import Enum
from typing import Any

from pydantic import BaseModel

from prediction_market_agent_tooling.gtypes import Probability
from prediction_market_agent_tooling.tools.utils import DatetimeUTC


class QuestionType(str, Enum):
    binary = "binary"


class AggregationItem(BaseModel):
    start_time: DatetimeUTC
    end_time: DatetimeUTC | None
    forecast_values: list[float] | None
    forecaster_count: int
    interval_lower_bounds: list[float] | None
    centers: list[float] | None
    interval_upper_bounds: list[float] | None
    means: list[float] | None
    histogram: list[float] | None


class Aggregation(BaseModel):
    history: list[AggregationItem]
    latest: AggregationItem | None
    score_data: dict[str, Any]


class Aggregations(BaseModel):
    recency_weighted: Aggregation
    unweighted: Aggregation
    single_aggregation: Aggregation
    metaculus_prediction: Aggregation


class MyForecast(BaseModel):
    start_time: DatetimeUTC
    end_time: DatetimeUTC | None
    forecast_values: list[float] | None
    interval_lower_bounds: list[float] | None
    centers: list[float] | None
    interval_upper_bounds: list[float] | None


class MyAggregation(BaseModel):
    history: list[MyForecast]
    latest: MyForecast | None
    score_data: dict[str, Any]


class Question(BaseModel):
    aggregations: Aggregations
    my_forecasts: MyAggregation
    type: QuestionType
    possibilities: dict[str, str] | None
    description: str
    fine_print: str
    resolution_criteria: str


class MetaculusQuestion(BaseModel):
    id: int
    author_id: int
    author_username: str
    title: str
    created_at: DatetimeUTC
    published_at: DatetimeUTC | None
    scheduled_close_time: DatetimeUTC
    scheduled_resolve_time: DatetimeUTC
    user_permission: str
    comment_count: int
    question: Question
    # TODO add the rest of the fields https://github.com/gnosis/prediction-market-agent-tooling/issues/301

    @property
    def page_url(self) -> str:
        return f"https://www.metaculus.com/questions/{self.id}/"

    @property
    def p_yes(self) -> Probability:
        if self.question.type != QuestionType.binary:
            raise ValueError(f"Only binary markets can have p_yes.")
        if (
            self.question.aggregations.recency_weighted is None
            or self.question.aggregations.recency_weighted.latest is None
            or self.question.aggregations.recency_weighted.latest.forecast_values
            is None
        ):
            # If no value is provided (i.e. the question is new and has not been answered yet), we default to 0.5.
            return Probability(0.5)
        if len(self.question.aggregations.recency_weighted.latest.forecast_values) != 2:
            raise ValueError(
                f"Invalid logic, assumed that binary markets will have two forecasts, got: {self.question.aggregations.recency_weighted.latest.forecast_values}"
            )
        # Experimentally figured out that they store "Yes" at index 1.
        return Probability(
            self.question.aggregations.recency_weighted.latest.forecast_values[1]
        )


class MetaculusQuestions(BaseModel):
    next: str | None
    previous: str | None
    results: list[MetaculusQuestion]
