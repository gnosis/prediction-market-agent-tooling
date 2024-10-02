import typing as t
from datetime import timedelta

import tenacity
from loguru import logger
from pydantic import BaseModel
from sqlalchemy import Column
from sqlalchemy.dialects.postgresql import JSONB
from sqlmodel import (
    ARRAY,
    Field,
    Session,
    SQLModel,
    String,
    create_engine,
    desc,
    select,
)

from prediction_market_agent_tooling.config import APIKeys
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


class TavilyStorage:
    def __init__(self, agent_id: str, sqlalchemy_db_url: str | None = None):
        self.agent_id = agent_id
        self.engine = create_engine(
            sqlalchemy_db_url
            if sqlalchemy_db_url
            else APIKeys().sqlalchemy_db_url.get_secret_value()
        )
        self._initialize_db()

    def _initialize_db(self) -> None:
        """
        Creates the tables if they don't exist
        """

        # trick for making models import mandatory - models must be imported for metadata.create_all to work
        logger.debug(f"tables being added {TavilyResponseModel}")
        SQLModel.metadata.create_all(self.engine)

    @tenacity.retry(stop=tenacity.stop_after_attempt(3), wait=tenacity.wait_fixed(1))
    def save(
        self,
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
        response: TavilyResponse,
    ) -> None:
        db_item = TavilyResponseModel.from_model(
            agent_id=self.agent_id,
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
            response=response,
        )
        with Session(self.engine) as session:
            session.add(db_item)
            session.commit()

    @tenacity.retry(stop=tenacity.stop_after_attempt(3), wait=tenacity.wait_fixed(1))
    def find(
        self,
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
        max_age: timedelta = timedelta(days=1),
    ) -> TavilyResponse | None:
        with Session(self.engine) as session:
            sql_query = (
                select(TavilyResponseModel)
                .where(TavilyResponseModel.query == query)
                .where(TavilyResponseModel.search_depth == search_depth)
                .where(TavilyResponseModel.topic == topic)
                .where(TavilyResponseModel.max_results == max_results)
                .where(TavilyResponseModel.include_domains == include_domains)
                .where(TavilyResponseModel.exclude_domains == exclude_domains)
                .where(TavilyResponseModel.include_answer == include_answer)
                .where(TavilyResponseModel.include_raw_content == include_raw_content)
                .where(TavilyResponseModel.include_images == include_images)
                .where(TavilyResponseModel.use_cache == use_cache)
                .where(TavilyResponseModel.datetime_ >= utcnow() - max_age)
            )
            item = session.exec(
                sql_query.order_by(desc(TavilyResponseModel.datetime_))
            ).first()
            return TavilyResponse.model_validate(item.response) if item else None
