from unittest.mock import patch

import pytest
from langchain_community.callbacks import get_openai_callback
from pydantic import SecretStr

from prediction_market_agent_tooling.config import APIKeys
from prediction_market_agent_tooling.tools.relevant_news_analysis.data_models import (
    RelevantNews,
)
from prediction_market_agent_tooling.tools.relevant_news_analysis.relevant_news_analysis import (
    get_certified_relevant_news_since,
    get_certified_relevant_news_since_cached,
)
from prediction_market_agent_tooling.tools.relevant_news_analysis.relevant_news_cache import (
    RelevantNewsResponseCache,
)
from tests.utils import RUN_PAID_TESTS


@pytest.mark.skipif(not RUN_PAID_TESTS, reason="This test costs money to run.")
def test_get_certified_relevant_news_since() -> None:
    questions_days_ago_expected_results = [
        (
            "Will the price of Bitcoin be higher than $100,000 by the end of the year?",
            True,
            5,
        ),
        (
            "Will the strength of the Earth's gravitational field change by more than 3% any time before the end of the calendar year?",
            False,
            2,
        ),
        (
            "Will the number of Chinese-made electric cars sold worldwide this year be higher than in the previous calendar year?",
            True,
            90,
        ),
        (
            "Will total UK cinema box office sales this month be higher than in the previous calendar month?",
            True,
            14,
        ),
    ]

    running_cost = 0.0
    iterations = 0
    for question, expected_result, days_ago in questions_days_ago_expected_results:
        with get_openai_callback() as cb:
            news = get_certified_relevant_news_since(
                question=question,
                days_ago=days_ago,
            )
            running_cost += cb.total_cost
            iterations += 1

        has_related_news = news is not None
        assert (
            has_related_news == expected_result
        ), f"Was relevant news found for question '{question}'?: {has_related_news}. Expected result {expected_result}"

    average_cost = running_cost / iterations  # $0.01289 when run on 2022-10-24
    assert average_cost < 0.02, f"Expected average: {average_cost}. Expected < 0.02"


def test_get_certified_relevant_news_since_cached() -> None:
    cache = RelevantNewsResponseCache(
        APIKeys(SQLALCHEMY_DB_URL=SecretStr("sqlite:///:memory:"))
    )

    question = (
        "Will the price of Bitcoin be higher than $100,000 by the end of the year?"
    )
    days_ago = 5
    assert (
        cache.find(question=question, days_ago=days_ago) is None
    ), "Cache should be empty"

    mock_news = RelevantNews(
        question=question,
        url="https://www.example.com",
        summary="This is a summary",
        relevance_reasoning="some reasoning",
        days_ago=days_ago,
    )
    with patch(
        "prediction_market_agent_tooling.tools.relevant_news_analysis.relevant_news_analysis.get_certified_relevant_news_since"
    ) as get_certified_relevant_news_since:
        # Mock the response
        get_certified_relevant_news_since.return_value = mock_news

        news = get_certified_relevant_news_since_cached(
            question=question,
            days_ago=1,
            cache=cache,
        )

    assert news == mock_news
    assert (
        cache.find(question=question, days_ago=days_ago) == mock_news
    ), "Cache should contain the news"
