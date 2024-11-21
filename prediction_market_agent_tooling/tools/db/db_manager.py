import hashlib
from contextlib import contextmanager
from typing import Generator, Sequence, cast

from sqlalchemy import Connection
from sqlmodel import Session, SQLModel, create_engine

from prediction_market_agent_tooling.config import APIKeys
from prediction_market_agent_tooling.tools.caches.serializers import (
    json_deserializer,
    json_serializer,
)


class DBManager:
    _instances: dict[str, "DBManager"] = {}

    def __new__(cls, api_keys: APIKeys | None = None) -> "DBManager":
        sqlalchemy_db_url = (api_keys or APIKeys()).sqlalchemy_db_url
        secret_value = sqlalchemy_db_url.get_secret_value()
        url_hash = hashlib.md5(secret_value.encode()).hexdigest()
        if url_hash not in cls._instances:
            instance = super(DBManager, cls).__new__(cls)
            cls._instances[url_hash] = instance
        return cls._instances[url_hash]

    def __init__(self, api_keys: APIKeys | None = None) -> None:
        if hasattr(self, "_engine"):
            return
        sqlalchemy_db_url = (api_keys or APIKeys()).sqlalchemy_db_url
        self._engine = create_engine(
            sqlalchemy_db_url.get_secret_value(),
            json_serializer=json_serializer,
            json_deserializer=json_deserializer,
            pool_size=20,
            pool_recycle=3600,
            echo=True,
        )
        self.cache_table_initialized: dict[str, bool] = {}

    @contextmanager
    def get_session(self) -> Generator[Session, None, None]:
        with Session(self._engine) as session:
            yield session

    @contextmanager
    def get_connection(self) -> Generator[Connection, None, None]:
        with self.get_session() as session:
            yield session.connection()

    def create_tables(
        self, sqlmodel_tables: Sequence[type[SQLModel]] | None = None
    ) -> None:
        tables_to_create = (
            [
                table
                for sqlmodel_table in sqlmodel_tables
                if not self.cache_table_initialized.get(
                    (
                        table := SQLModel.metadata.tables[
                            cast(str, sqlmodel_table.__tablename__)
                        ]
                    ).name
                )
            ]
            if sqlmodel_tables is not None
            else None
        )
        SQLModel.metadata.create_all(self._engine, tables=tables_to_create)

        for table in tables_to_create or []:
            self.cache_table_initialized[table.name] = True
