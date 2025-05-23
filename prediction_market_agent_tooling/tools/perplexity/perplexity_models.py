from typing import Any, List, Literal, Optional

from pydantic import BaseModel


class PerplexityRequestParameters(BaseModel):
    search_context_size: Optional[Literal["low", "medium", "high"]]
    search_recency_filter: Optional[Literal["any", "day", "week", "month", "year"]]
    search_return_related_questions: Optional[bool]
    search_domain_filter: Optional[List[str]]
    search_after_date_filter: Optional[str]
    search_before_date_filter: Optional[str]


class PerplexityResponse(BaseModel):
    content: str
    citations: list[str]
    usage: dict[str, Any]


class PerplexityModelSettings(BaseModel):
    max_tokens: Optional[int] = None
    temperature: Optional[float] = None
    top_p: Optional[float] = None
    frequency_penalty: Optional[float] = None
    presence_penalty: Optional[float] = None
