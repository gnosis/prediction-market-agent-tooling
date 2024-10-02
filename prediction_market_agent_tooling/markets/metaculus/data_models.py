from enum import Enum
from typing import Any

from pydantic import BaseModel

from prediction_market_agent_tooling.tools.utils import DatetimeUTCValidator


class QuestionType(str, Enum):
    forecast = "forecast"
    notebook = "notebook"
    discussion = "discussion"
    claim = "claim"
    group = "group"
    conditional_group = "conditional_group"
    multiple_choice = "multiple_choice"


class CommunityPrediction(BaseModel):
    y: list[float]
    q1: float | None = None
    q2: float | None = None
    q3: float | None = None

    @property
    def p_yes(self) -> float:
        """
        q2 corresponds to the median, or 'second quartile' of the distribution.

        If no value is provided (i.e. the question is new and has not been
        answered yet), we default to 0.5.
        """
        return self.q2 if self.q2 is not None else 0.5


class Prediction(BaseModel):
    t: DatetimeUTCValidator
    x: float


class UserPredictions(BaseModel):
    id: int
    predictions: list[Prediction]
    points_won: float | None = None
    user: int
    username: str
    question: int


class CommunityPredictionStats(BaseModel):
    full: CommunityPrediction
    unweighted: CommunityPrediction


class MetaculusQuestion(BaseModel):
    """
    https://www.metaculus.com/api2/schema/redoc/#tag/questions/operation/questions_retrieve
    """

    active_state: Any
    url: str
    page_url: str
    id: int
    author: int
    author_name: str
    author_id: int
    title: str
    title_short: str
    group_label: str | None = None
    resolution: int | None
    resolved_option: int | None
    created_time: DatetimeUTCValidator
    publish_time: DatetimeUTCValidator | None = None
    close_time: DatetimeUTCValidator | None = None
    effected_close_time: DatetimeUTCValidator | None
    resolve_time: DatetimeUTCValidator | None = None
    possibilities: dict[Any, Any] | None = None
    scoring: dict[Any, Any] = {}
    type: QuestionType | None = None
    user_perms: Any
    weekly_movement: float | None
    weekly_movement_direction: int | None = None
    cp_reveal_time: DatetimeUTCValidator | None = None
    edited_time: DatetimeUTCValidator
    last_activity_time: DatetimeUTCValidator
    activity: float
    comment_count: int
    votes: int
    community_prediction: CommunityPredictionStats
    my_predictions: UserPredictions | None = None
    # TODO add the rest of the fields https://github.com/gnosis/prediction-market-agent-tooling/issues/301


class MetaculusQuestions(BaseModel):
    next: str | None
    previous: str | None
    results: list[MetaculusQuestion]
