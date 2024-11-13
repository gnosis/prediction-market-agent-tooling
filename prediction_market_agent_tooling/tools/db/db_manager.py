from contextlib import contextmanager
from typing import Sequence

from sqlalchemy import Connection, Table
from sqlmodel import create_engine, Session, SQLModel

from prediction_market_agent_tooling.config import APIKeys
from prediction_market_agent_tooling.tools.caches.serializers import (
    json_serializer,
    json_deserializer,
)
from prediction_market_agent_tooling.tools.singleton import SingletonMeta


class DBManager(metaclass=SingletonMeta):
    def __init__(self, api_keys: APIKeys) -> None:
        # We pass in serializers as used by db_cache (no reason not to).
        self._engine = create_engine(
            api_keys.sqlalchemy_db_url.get_secret_value(),
            json_serializer=json_serializer,
            json_deserializer=json_deserializer,
            pool_size=20,
            pool_recycle=3600,
            echo=True
        )
        self.cache_table_initialized = False

    @contextmanager
    def get_session(self) -> Session:
        session = Session(self._engine)
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()  # Rollback if there's an error
            raise  # Propagate the exception
        finally:
            session.close()

    @contextmanager
    def get_connection(self) -> Connection:
        with self.get_session() as session:
            yield session.connection()

    def init_cache_metadata(self, tables: Sequence[Table]|None=None) -> None:
        if not self.cache_table_initialized:
            with self.get_connection() as conn:
                SQLModel.metadata.create_all(conn, tables=tables)

        self.cache_table_initialized = True