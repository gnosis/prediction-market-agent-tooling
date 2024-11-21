import tempfile

from pydantic import SecretStr

from prediction_market_agent_tooling.tools.db.db_manager import APIKeys, DBManager


def test_DBManager_creates_only_one_instance() -> None:
    with tempfile.NamedTemporaryFile(
        suffix=".db"
    ) as temp_db1, tempfile.NamedTemporaryFile(suffix=".db") as temp_db3:
        db1 = DBManager(
            APIKeys(SQLALCHEMY_DB_URL=SecretStr(f"sqlite:///{temp_db1.name}"))
        )
        db2 = DBManager(
            APIKeys(SQLALCHEMY_DB_URL=SecretStr(f"sqlite:///{temp_db1.name}"))
        )
        db3 = DBManager(
            APIKeys(SQLALCHEMY_DB_URL=SecretStr(f"sqlite:///{temp_db3.name}"))
        )
        are_same_instance = db1 is db2
        are_not_same_instance = db1 is not db3

    assert are_same_instance, "DBManager created more than one instance!"
    assert (
        are_not_same_instance
    ), "DBManager returned isntance with a different SQLALCHEMY_DB_URL!"


# TODO: Gabriel what was the goal in this test?
# def test_session_can_be_used_by_metadata() -> None:
#     db = DBManager()
#     session = db.get_session()
#     # ToDo - add more tests
#     SQLModel.metadata.create_all(session.bind)
