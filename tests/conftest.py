from typing import Generator

import psycopg
import pytest
from pydantic.types import SecretStr

from prediction_market_agent_tooling.config import APIKeys


@pytest.fixture
def keys_with_sqlalchemy_db_url(
    postgresql: psycopg.Connection,
) -> Generator[APIKeys, None, None]:
    sqlalchemy_db_url = f"postgresql+psycopg2://{postgresql.info.user}:@{postgresql.info.host}:{postgresql.info.port}/{postgresql.info.dbname}"
    yield APIKeys(SQLALCHEMY_DB_URL=SecretStr(sqlalchemy_db_url), ENABLE_CACHE=True)
