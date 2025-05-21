import re
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, HttpUrl, field_validator
from pydantic_ai.models import ModelRequestParameters
from pydantic_ai.tools import ToolDefinition


class PerplexityRequestParameters(ModelRequestParameters):
    def __init__(
        self,
        function_tools: List[ToolDefinition] = [],
        allow_text_output: bool = True,
        output_tools: List[ToolDefinition] = [],
        search_context_size: Optional[Literal["low", "medium", "high"]] = None,
        search_recency_filter: Optional[
            Literal["any", "day", "week", "month", "year"]
        ] = None,
        search_return_related_questions: Optional[bool] = None,
        search_domain_filter: Optional[List[str]] = None,
        search_after_date_filter: Optional[str] = None,
        search_before_date_filter: Optional[str] = None,
        **kwargs: Dict[str, Any]
    ) -> None:
        # Initialize base class with required parameters
        super().__init__(
            function_tools=function_tools,
            allow_text_output=allow_text_output,
            output_tools=output_tools,
        )

        # Set Perplexity-specific parameters
        self.search_context_size = search_context_size
        self.search_recency_filter = search_recency_filter
        self.search_return_related_questions = search_return_related_questions
        self.search_domain_filter = search_domain_filter
        self.search_after_date_filter = search_after_date_filter
        self.search_before_date_filter = search_before_date_filter

    @field_validator("search_after_date_filter", "search_before_date_filter")
    @classmethod
    def validate_date_format(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return value
        if not re.match(r"^\d{4}-\d{2}-\d{2}$", value):
            raise ValueError("Date must be in YYYY-MM-DD format")
        return value


class Message(BaseModel):
    role: str
    content: str


class PerplexityResult(BaseModel):
    title: str
    url: HttpUrl
    snippet: str
    score: float


class PerplexityResponse(BaseModel):
    content: str
    citations: list[str]
    usage: dict[str, Any]
