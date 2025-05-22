import asyncio
import typing as t
from datetime import date

import tenacity

from prediction_market_agent_tooling.config import APIKeys
from prediction_market_agent_tooling.tools.perplexity.perplexity_client import (
    PerplexityModel,
)
from prediction_market_agent_tooling.tools.perplexity.perplexity_models import (
    PerplexityModelSettings,
    PerplexityRequestParameters,
    PerplexityResponse,
)

DEFAULT_SCORE_THRESHOLD = 0.75
SYSTEM_PROMPT = "You are a helpful search assistant. Your task is to provide accurate information based on web searches."


# @db_cache(
#     max_age=timedelta(days=1),
#     ignore_args=["api_keys"],
#     log_error_on_unsavable_data=False,
# )
@tenacity.retry(stop=tenacity.stop_after_attempt(3), wait=tenacity.wait_fixed(1))
def perplexity_search(
    query: str,
    search_context_size: t.Literal["low", "medium", "high"] = "medium",
    search_recency_filter: t.Literal["any", "day", "week", "month", "year"]
    | None = None,
    search_filter_before_date: date | None = None,
    search_filter_after_date: date | None = None,
    search_return_related_questions: bool | None = None,
    include_domains: list[str] | None = None,
    temperature: float = 0,
    model_name: str = "sonar-pro",
    max_tokens: int = 2048,
    api_keys: APIKeys | None = None,
) -> PerplexityResponse:
    if api_keys is None:
        raise ValueError("API keys are required")

    # Create messages in ModelMessage format
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": query},
    ]

    # Define special parameters for the request and create the settings
    model_settings = PerplexityModelSettings(
        max_tokens=max_tokens, temperature=temperature
    )

    # Create a basic request parameters object with required base parameters
    request_params = PerplexityRequestParameters(
        search_domain_filter=include_domains,
        search_after_date_filter=search_filter_after_date.strftime("%Y-%m-%d")
        if search_filter_after_date
        else None,
        search_before_date_filter=search_filter_before_date.strftime("%Y-%m-%d")
        if search_filter_before_date
        else None,
        search_recency_filter=search_recency_filter,
        search_context_size=search_context_size,
        search_return_related_questions=search_return_related_questions,
    )

    model = PerplexityModel(
        model_name=model_name, api_key=api_keys.perplexity_api_key.get_secret_value()
    )
    return asyncio.run(
        model.request(
            messages=messages,
            model_settings=model_settings,
            model_request_parameters=request_params,
        )
    )
