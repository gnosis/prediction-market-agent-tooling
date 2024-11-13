import typing as t
from unittest.mock import patch

import pytest
from pydantic import SecretStr
from sqlmodel import SQLModel

from prediction_market_agent_tooling.config import APIKeys
from prediction_market_agent_tooling.tools.db.db_manager import DBManager


@pytest.fixture(scope="module")
def random_api_keys_with_sqlalchemy_db_url() -> t.Generator[APIKeys,None,None]:
    with patch("prediction_market_agent_tooling.config.APIKeys.sqlalchemy_db_url", SecretStr("abc")):
        keys = APIKeys()
    yield keys

def test_DBManager_creates_only_one_instance(random_api_keys_with_sqlalchemy_db_url: APIKeys) -> None:

    db1 = DBManager(random_api_keys_with_sqlalchemy_db_url)
    db2 = DBManager(random_api_keys_with_sqlalchemy_db_url)
    are_same_instance = db1 is db2
    assert are_same_instance, "DBManager created more than one instance!"


def test_session_can_be_used_by_metadata() -> None:
    db = DBManager()
    session = db.get_session()
    # ToDo - add more tests
    SQLModel.metadata.create_all(session.bind)
