from langchain_community.callbacks import get_openai_callback

from prediction_market_agent_tooling.tools.relevant_news_analysis import (
    get_certified_relevant_news_since,
)


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
                model="gpt-4o",
            )
            running_cost += cb.total_cost
            iterations += 1

        has_related_news = news is not None
        assert (
            has_related_news == expected_result
        ), f"Was relevant news found for question '{question}'?: {has_related_news}. Expected result {expected_result}"

    average_cost = running_cost / iterations
    assert average_cost < 0.03, f"Expected average: {average_cost}. Expected < 0.03"
