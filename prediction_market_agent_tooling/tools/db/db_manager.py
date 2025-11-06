import asyncio
import hashlib
import threading
from contextlib import contextmanager
from typing import Generator, Sequence

from pydantic import SecretStr
from sqlalchemy import Connection
from sqlmodel import Session, SQLModel, create_engine

from prediction_market_agent_tooling.config import APIKeys
from prediction_market_agent_tooling.tools.caches.serializers import (
    json_deserializer,
    json_serializer,
)


class DBManager:
    _instances: dict[str, "DBManager"] = {}

    def __new__(cls, sqlalchemy_db_url: str | None = None) -> "DBManager":
        if sqlalchemy_db_url is None:
            sqlalchemy_db_url = APIKeys().sqlalchemy_db_url.get_secret_value()

        # Hash the secret value to not store secrets in plain text.
        url_hash = hashlib.md5(sqlalchemy_db_url.encode()).hexdigest()
        # Return singleton per database connection.
        if url_hash not in cls._instances:
            instance = super(DBManager, cls).__new__(cls)
            cls._instances[url_hash] = instance
        return cls._instances[url_hash]

    def __init__(self, sqlalchemy_db_url: str | None = None) -> None:
        if hasattr(self, "_initialized"):
            return
        sqlalchemy_db_url = (
            sqlalchemy_db_url or APIKeys().sqlalchemy_db_url.get_secret_value()
        )
        self._engine = create_engine(
            sqlalchemy_db_url,
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


class EnsureTableManager:
    """
    Manages database table initialization with thread-safe and async-safe locking.
    Ensures tables are created only once per database URL.
    """

    def __init__(self, tables: Sequence[type[SQLModel]]) -> None:
        """
        Initialize the table manager with the tables to manage.

        Args:
            tables: Sequence of SQLModel table classes to ensure in the database.
        """
        # Ensure tables only once, as it's a time costly operation.
        self._tables = tables
        self._lock_thread = threading.Lock()
        self._lock_async = asyncio.Lock()
        self._ensured: dict[SecretStr, bool] = {}

    def is_ensured(self, db_url: SecretStr) -> bool:
        """Check if tables have been ensured for the given database URL."""
        return self._ensured.get(db_url, False)

    def mark_ensured(self, db_url: SecretStr) -> None:
        """Mark tables as ensured for the given database URL."""
        self._ensured[db_url] = True

    def ensure_tables_sync(self, api_keys: APIKeys) -> None:
        """
        Ensure tables exist for the given API keys (synchronous version).
        Thread-safe with double-checked locking pattern.
        """
        if not self.is_ensured(api_keys.sqlalchemy_db_url):
            with self._lock_thread:
                if not self.is_ensured(api_keys.sqlalchemy_db_url):
                    self._create_tables(api_keys)
                    self.mark_ensured(api_keys.sqlalchemy_db_url)

    async def ensure_tables_async(self, api_keys: APIKeys) -> None:
        """
        Ensure tables exist for the given API keys (asynchronous version).
        Async-safe with double-checked locking pattern.
        """
        if not self.is_ensured(api_keys.sqlalchemy_db_url):
            async with self._lock_async:
                if not self.is_ensured(api_keys.sqlalchemy_db_url):
                    await asyncio.to_thread(self._create_tables, api_keys)
                    self.mark_ensured(api_keys.sqlalchemy_db_url)

    def _create_tables(self, api_keys: APIKeys) -> None:
        """Create the database tables."""
        DBManager(api_keys.sqlalchemy_db_url.get_secret_value()).create_tables(
            list(self._tables)
        )
