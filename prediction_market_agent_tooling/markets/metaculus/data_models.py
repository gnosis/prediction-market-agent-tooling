from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel


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

        If no value is provided, we default to 0.5.
        """
        return self.q2 if self.q2 is not None else 0.5


class Prediction(BaseModel):
    t: datetime
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
    created_time: datetime
    publish_time: datetime | None = None
    close_time: datetime | None = None
    effected_close_time: datetime | None
    resolve_time: datetime | None = None
    possibilities: dict[Any, Any] | None = None
    scoring: dict[Any, Any] = {}
    type: QuestionType | None = None
    user_perms: Any
    weekly_movement: float | None
    weekly_movement_direction: int | None = None
    cp_reveal_time: datetime | None = None
    edited_time: datetime
    last_activity_time: datetime
    activity: float
    comment_count: int
    votes: int
    community_prediction: CommunityPredictionStats
    my_predictions: UserPredictions | None = None
    # TODO add the rest of the fields
    # metaculus_prediction
    # number_of_forecasters
    # prediction_count
    # approved_by
    # approved_time
    # approved_by_id
    # related_questions
    # group
    # condition
    # sub_questions
    # total_sub_question_count
    # options
    # has_fan_graph
    # image_url
    # projects
    # primary_project
    # medals_end_year
    # medals_duration
    # unweighted_community_prediction_v2
    # recency_weighted_community_prediction_v2
    # cp_baseline_score
    # cp_peer_score
    # summary
    # user_vote
    # divergence
    # peer_score
    # spot_peer_score
    # baseline_score
    # user_prediction_sequence
    # anon_prediction_count
    # description
    # description_html
    # resolution_criteria
    # resolution_criteria_html
    # fine_print
    # fine_print_html
    # user_predictions
    # tags
    # categories
    # categories_extended
    # closing_bonus
    # cp_hidden_weight_coverage
    # graph_image_url
    # sponsors
    # shared_with
    # simplified_history: dict
    # status
