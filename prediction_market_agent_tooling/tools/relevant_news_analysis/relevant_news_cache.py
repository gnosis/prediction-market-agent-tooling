from datetime import datetime, timedelta

from pydantic import ValidationError
from sqlmodel import Field, Session, SQLModel, create_engine, desc, select

from prediction_market_agent_tooling.config import APIKeys
from prediction_market_agent_tooling.loggers import logger
from prediction_market_agent_tooling.tools.relevant_news_analysis.data_models import (
    NoRelevantNews,
    RelevantNews,
)
from prediction_market_agent_tooling.tools.utils import check_not_none, utcnow


class RelevantNewsCacheModel(SQLModel, table=True):
    __tablename__ = "relevant_news_response_cache"
    __table_args__ = {"extend_existing": True}
    id: int | None = Field(default=None, primary_key=True)
    question: str = Field(index=True)
    datetime_: datetime = Field(index=True)
    days_ago: int
    json_dump: str | None


class RelevantNewsResponseCache:
    def __init__(self, sqlalchemy_db_url: str | None = None):
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
        with self.engine.connect() as conn:
            SQLModel.metadata.create_all(
                conn,
                tables=[SQLModel.metadata.tables[RelevantNewsCacheModel.__tablename__]],
            )

    def find(
        self,
        question: str,
        days_ago: int,
    ) -> RelevantNews | NoRelevantNews | None:
        with Session(self.engine) as session:
            query = (
                select(RelevantNewsCacheModel)
                .where(RelevantNewsCacheModel.question == question)
                .where(RelevantNewsCacheModel.days_ago <= days_ago)
                .where(
                    RelevantNewsCacheModel.datetime_ >= utcnow() - timedelta(days=1)
                )  # Cache entries expire after 1 day
            )
            item = session.exec(
                query.order_by(desc(RelevantNewsCacheModel.datetime_))
            ).first()

            if item is None:
                return None
            else:
                item = check_not_none(item)
                if item.json_dump is None:
                    return NoRelevantNews()
                else:
                    try:
                        return RelevantNews.model_validate_json(item.json_dump)
                    except ValidationError as e:
                        logger.error(
                            f"Error deserializing RelevantNews from cache for {question=}, {days_ago=} and {item=}: {e}"
                        )
                        return None

    def save(
        self,
        question: str,
        days_ago: int,
        relevant_news: RelevantNews | None,
    ) -> None:
        with Session(self.engine) as session:
            cached = RelevantNewsCacheModel(
                question=question,
                days_ago=days_ago,
                datetime_=utcnow(),  # Assumes that the cache is being updated at the time the news is found
                json_dump=relevant_news.model_dump_json() if relevant_news else None,
            )
            session.add(cached)
            session.commit()
