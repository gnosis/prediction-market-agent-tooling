import hashlib
from contextlib import contextmanager
from typing import Generator, Sequence

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
        # Hash the secret value to not store secrets in plain text.
        url_hash = hashlib.md5(
            sqlalchemy_db_url.get_secret_value().encode()
        ).hexdigest()
        # Return singleton per database connection.
        if url_hash not in cls._instances:
            instance = super(DBManager, cls).__new__(cls)
            cls._instances[url_hash] = instance
        return cls._instances[url_hash]

    def __init__(self, api_keys: APIKeys | None = None) -> None:
        if hasattr(self, "_initialized"):
            return
        sqlalchemy_db_url = (api_keys or APIKeys()).sqlalchemy_db_url
        self._engine = create_engine(
            sqlalchemy_db_url.get_secret_value(),
            json_serializer=json_serializer,
            json_deserializer=json_deserializer,
            pool_size=2,
        )
        self.cache_table_initialized: dict[str, bool] = {}
        self._initialized = True

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
        # Determine tables to create
        if sqlmodel_tables is not None:
            tables_to_create = []
            for sqlmodel_table in sqlmodel_tables:
                table_name = (
                    sqlmodel_table.__tablename__()
                    if callable(sqlmodel_table.__tablename__)
                    else sqlmodel_table.__tablename__
                )
                table = SQLModel.metadata.tables[table_name]
                if not self.cache_table_initialized.get(table.name):
                    tables_to_create.append(table)
        else:
            tables_to_create = None

        # Create tables in the database
        if tables_to_create is None or len(tables_to_create) > 0:
            with self.get_connection() as connection:
                SQLModel.metadata.create_all(connection, tables=tables_to_create)
                connection.commit()

        # Update cache to mark tables as initialized
        if tables_to_create:
            for table in tables_to_create:
                self.cache_table_initialized[table.name] = True
