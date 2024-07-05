import json
from datetime import datetime
from typing import Union

import requests

from prediction_market_agent_tooling.config import APIKeys
from prediction_market_agent_tooling.gtypes import Probability
from prediction_market_agent_tooling.markets.metaculus.data_models import (
    MetaculusQuestion,
)

METACULUS_API_BASE_URL = "https://www.metaculus.com/api2"
WARMUP_TOURNAMENT_ID = 3294


def get_auth_headers() -> dict[str, str]:
    return {"Authorization": f"Token {APIKeys().metaculus_api_key.get_secret_value()}"}


def post_question_comment(question_id: str, comment_text: str) -> None:
    """
    Post a comment on the question page as the bot user.
    """

    response = requests.post(
        f"{METACULUS_API_BASE_URL}/comments/",
        json={
            "comment_text": comment_text,
            "submit_type": "N",
            "include_latest_prediction": True,
            "question": question_id,
        },
        headers=get_auth_headers(),
    )
    response.raise_for_status()


def make_prediction(question_id: str, p_yes: Probability) -> None:
    """
    Make a prediction for a question.
    """
    url = f"{METACULUS_API_BASE_URL}/questions/{question_id}/predict/"
    response = requests.post(
        url,
        json={"prediction": p_yes},
        headers=get_auth_headers(),
    )
    response.raise_for_status()


def get_question(question_id: str) -> MetaculusQuestion:
    """
    Get all details about a specific question.
    """
    url = f"{METACULUS_API_BASE_URL}/questions/{question_id}/"
    response = requests.get(url, headers=get_auth_headers())
    response.raise_for_status()
    response_json = json.loads(response.content)
    return MetaculusQuestion.model_validate(response_json)


def get_questions(
    limit: int,
    order_by: str | None = None,
    offset: int = 0,
    tournament_id: int | None = None,
    created_after: datetime | None = None,
    status: str | None = None,
) -> list[MetaculusQuestion]:
    """
    List (all details) {count} questions from the {tournament_id}
    """
    url_params: dict[str, Union[int, str]] = {
        "limit": limit,
        "offset": offset,
        "has_group": "false",
        "forecast_type": "binary",
        "type": "forecast",
        "include_description": "true",
    }
    if order_by:
        url_params["order_by"] = order_by
    if tournament_id:
        url_params["tournament"] = tournament_id
    if created_after:
        url_params["created_time__gt"] = created_after.isoformat()
    if status:
        url_params["status"] = status

    url = f"{METACULUS_API_BASE_URL}/questions/"
    response = requests.get(url, headers=get_auth_headers(), params=url_params)
    response.raise_for_status()
    response_json = json.loads(response.content)
    return [MetaculusQuestion.model_validate(q) for q in response_json["results"]]
