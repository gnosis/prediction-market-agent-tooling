from typing import Union

import requests

from prediction_market_agent_tooling.config import APIKeys
from prediction_market_agent_tooling.gtypes import Probability
from prediction_market_agent_tooling.markets.metaculus.data_models import (
    MetaculusQuestion,
    MetaculusQuestions,
)
from prediction_market_agent_tooling.tools.utils import DatetimeUTC, response_to_model

METACULUS_API_BASE_URL = "https://www.metaculus.com/api2"


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
    return response_to_model(
        response=requests.get(url, headers=get_auth_headers()),
        model=MetaculusQuestion,
    )


def get_questions(
    limit: int,
    order_by: str | None = None,
    offset: int = 0,
    tournament_id: int | None = None,
    created_after: DatetimeUTC | None = None,
    status: str | None = None,
) -> list[MetaculusQuestion]:
    """
    List detailed metaculus questions (i.e. markets)
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
        url_params["project"] = tournament_id
    if created_after:
        url_params["created_time__gt"] = created_after.isoformat()
    if status:
        url_params["status"] = status

    url = f"{METACULUS_API_BASE_URL}/questions/"
    return response_to_model(
        response=requests.get(url, headers=get_auth_headers(), params=url_params),
        model=MetaculusQuestions,
    ).results
