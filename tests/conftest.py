from typing import Generator

import pytest
from pydantic.types import SecretStr
from pytest_postgresql.executor import PostgreSQLExecutor
from pytest_postgresql.janitor import DatabaseJanitor

from prediction_market_agent_tooling.config import APIKeys


@pytest.fixture(scope="session")
def session_keys_with_postgresql_proc_and_enabled_cache(
    postgresql_proc: PostgreSQLExecutor,
) -> Generator[APIKeys, None, None]:
    with DatabaseJanitor(
        user=postgresql_proc.user,
        host=postgresql_proc.host,
        port=postgresql_proc.port,
        dbname=postgresql_proc.dbname,
        version=postgresql_proc.version,
    ):
        sqlalchemy_db_url = f"postgresql+psycopg2://{postgresql_proc.user}:@{postgresql_proc.host}:{postgresql_proc.port}/{postgresql_proc.dbname}"
        yield APIKeys(SQLALCHEMY_DB_URL=SecretStr(sqlalchemy_db_url), ENABLE_CACHE=True)
