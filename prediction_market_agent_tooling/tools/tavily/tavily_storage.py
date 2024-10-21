import typing as t
from datetime import timedelta

import tenacity
from sqlmodel import Session, SQLModel, create_engine, desc, select

from prediction_market_agent_tooling.config import APIKeys
from prediction_market_agent_tooling.loggers import logger
from prediction_market_agent_tooling.tools.tavily.tavily_models import (
    TavilyResponse,
    TavilyResponseModel,
)
from prediction_market_agent_tooling.tools.utils import utcnow


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
        days: int | None,
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
            days=days,
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
        days: int | None,
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
                .where(TavilyResponseModel.days == days)
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
