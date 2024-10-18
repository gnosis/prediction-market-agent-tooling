import typing as t

from pydantic import BaseModel
from sqlalchemy import Column
from sqlalchemy.dialects.postgresql import JSONB
from sqlmodel import ARRAY, Field, SQLModel, String

from prediction_market_agent_tooling.tools.utils import DatetimeUTC, utcnow


class TavilyResult(BaseModel):
    title: str
    url: str
    content: str
    score: float
    raw_content: str | None


class TavilyResponse(BaseModel):
    query: str
    follow_up_questions: None = None
    answer: str
    images: list[str]
    results: list[TavilyResult]
    response_time: float


class TavilyResponseModel(SQLModel, table=True):
    __tablename__ = "tavily_response"
    __table_args__ = {"extend_existing": True}
    id: int | None = Field(None, primary_key=True)
    agent_id: str = Field(index=True, nullable=False)
    # Parameters used to execute the search
    query: str = Field(index=True, nullable=False)
    search_depth: str
    topic: str
    days: int | None = Field(default=None, nullable=True)
    max_results: int
    include_domains: list[str] | None = Field(
        None, sa_column=Column(ARRAY(String), nullable=True)
    )
    exclude_domains: list[str] | None = Field(
        None, sa_column=Column(ARRAY(String), nullable=True)
    )
    include_answer: bool
    include_raw_content: bool
    include_images: bool
    use_cache: bool
    # Datetime at the time of search response and response from the search
    datetime_: DatetimeUTC = Field(index=True, nullable=False)
    response: dict[str, t.Any] = Field(sa_column=Column(JSONB, nullable=False))

    @staticmethod
    def from_model(
        agent_id: str,
        query: str,
        search_depth: t.Literal["basic", "advanced"],
        topic: t.Literal["general", "news"],
        days: int | None,
        max_results: int,
        include_domains: t.Sequence[str] | None,
        exclude_domains: t.Sequence[str] | None,
        include_answer: bool,
        include_raw_content: bool,
        include_images: bool,
        use_cache: bool,
        response: TavilyResponse,
    ) -> "TavilyResponseModel":
        return TavilyResponseModel(
            agent_id=agent_id,
            query=query,
            search_depth=search_depth,
            topic=topic,
            days=days,
            max_results=max_results,
            include_domains=sorted(include_domains) if include_domains else None,
            exclude_domains=sorted(exclude_domains) if exclude_domains else None,
            include_answer=include_answer,
            include_raw_content=include_raw_content,
            include_images=include_images,
            use_cache=use_cache,
            datetime_=utcnow(),
            response=response.model_dump(),
        )
