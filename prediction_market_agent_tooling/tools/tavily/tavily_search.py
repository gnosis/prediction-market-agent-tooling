import typing as t
from datetime import date, timedelta

import tenacity
from tavily import TavilyClient

from prediction_market_agent_tooling.config import APIKeys
from prediction_market_agent_tooling.tools.caches.db_cache import db_cache
from prediction_market_agent_tooling.tools.tavily.tavily_models import (
    TavilyResponse,
    TavilyResult,
)

DEFAULT_SCORE_THRESHOLD = 0.75  # Based on some empirical testing, anything lower wasn't very relevant to the question being asked


@db_cache(
    max_age=timedelta(days=1),
    ignore_args=["api_keys"],
    log_error_on_unsavable_data=False,
)
def tavily_search(
    query: str,
    search_depth: t.Literal["basic", "advanced"] = "advanced",
    topic: t.Literal["general", "news"] = "general",
    news_since: date | None = None,
    start_date: date | None = None,
    end_date: date | None = None,
    max_results: int = 5,
    include_domains: t.Sequence[str] | None = None,
    exclude_domains: t.Sequence[str] | None = None,
    include_answer: bool = True,
    include_raw_content: bool = True,
    include_images: bool = True,
    use_cache: bool = False,
    api_keys: APIKeys | None = None,
) -> TavilyResponse:
    """
    Argument default values are different from the original method, to return everything by default, because it can be handy in the future and it doesn't increase the costs.
    """
    if topic == "news" and news_since is None:
        raise ValueError("When topic is 'news', news_since must be provided")
    if topic == "general" and news_since is not None:
        raise ValueError("When topic is 'general', news_since must be None")

    days = None if news_since is None else (date.today() - news_since).days
    response = _tavily_search(
        query=query,
        search_depth=search_depth,
        topic=topic,
        max_results=max_results,
        days=days,
        start_date=start_date,
        end_date=end_date,
        include_domains=include_domains,
        exclude_domains=exclude_domains,
        include_answer=include_answer,
        include_raw_content=include_raw_content,
        include_images=include_images,
        use_cache=use_cache,
        api_keys=api_keys,
    )
    response_parsed = TavilyResponse.model_validate(response)

    return response_parsed


@tenacity.retry(stop=tenacity.stop_after_attempt(3), wait=tenacity.wait_fixed(1))
def _tavily_search(
    query: str,
    search_depth: t.Literal["basic", "advanced"],
    topic: t.Literal["general", "news"],
    days: int | None,
    start_date: date | None,
    end_date: date | None,
    max_results: int,
    include_domains: t.Sequence[str] | None,
    exclude_domains: t.Sequence[str] | None,
    include_answer: bool,
    include_raw_content: bool,
    include_images: bool,
    use_cache: bool,
    api_keys: APIKeys | None = None,
) -> dict[str, t.Any]:
    """
    Internal minimalistic wrapper around Tavily's search method, that will retry if the call fails.
    """
    tavily = TavilyClient(
        api_key=(api_keys or APIKeys()).tavily_api_key.get_secret_value()
    )

    # Optional args can only be specified if not None, otherwise Tavily
    # will throw an error
    kwargs: dict[str, t.Any] = {}
    if days:
        kwargs["days"] = days
    if start_date is not None:
        kwargs["start_date"] = start_date.isoformat()
    if end_date is not None:
        kwargs["end_date"] = end_date.isoformat()

    response: dict[str, t.Any] = tavily.search(
        query=query,
        search_depth=search_depth,
        topic=topic,
        max_results=max_results,
        include_domains=include_domains,
        exclude_domains=exclude_domains,
        include_answer=include_answer,
        include_raw_content=include_raw_content,
        include_images=include_images,
        use_cache=use_cache,
        **kwargs,
    )
    return response


def get_relevant_news_since(
    question: str,
    news_since: date,
    score_threshold: float = DEFAULT_SCORE_THRESHOLD,
    max_results: int = 3,
) -> list[TavilyResult]:
    news = tavily_search(
        query=question,
        news_since=news_since,
        max_results=max_results,
        topic="news",
    )
    return [r for r in news.results if r.score > score_threshold]
