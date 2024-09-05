import typing as t

import tenacity
from tavily import TavilyClient

from prediction_market_agent_tooling.config import APIKeys
from prediction_market_agent_tooling.tools.tavily_storage.tavily_models import (
    TavilyResponse,
    TavilyStorage,
)


def tavily_search(
    query: str,
    search_depth: t.Literal["basic", "advanced"] = "advanced",
    topic: t.Literal["general", "news"] = "general",
    max_results: int = 5,
    include_domains: t.Sequence[str] | None = None,
    exclude_domains: t.Sequence[str] | None = None,
    include_answer: bool = True,
    include_raw_content: bool = True,
    include_images: bool = True,
    use_cache: bool = False,
    api_keys: APIKeys | None = None,
    tavily_storage: TavilyStorage | None = None,
) -> TavilyResponse:
    """
    Wrapper around Tavily's search method that will save the response to `TavilyResponseCache`, if provided.

    Argument default values are different from the original method, to return everything by default, because it can be handy in the future and it doesn't increase the costs.
    """
    if tavily_storage and (
        response_parsed := tavily_storage.find(
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
        )
    ):
        return response_parsed
    response = _tavily_search(
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
        api_keys=api_keys,
    )
    response_parsed = TavilyResponse.model_validate(response)
    if tavily_storage:
        tavily_storage.save(
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
            response=response_parsed,
        )
    return response_parsed


@tenacity.retry(stop=tenacity.stop_after_attempt(3), wait=tenacity.wait_fixed(1))
def _tavily_search(
    query: str,
    search_depth: t.Literal["basic", "advanced"],
    topic: t.Literal["general", "news"],
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
    )
    return response
