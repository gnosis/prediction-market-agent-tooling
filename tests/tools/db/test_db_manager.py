import tempfile

from prediction_market_agent_tooling.tools.db.db_manager import DBManager


def test_DBManager_creates_only_one_instance() -> None:
    with tempfile.NamedTemporaryFile(
        suffix=".db"
    ) as temp_db1, tempfile.NamedTemporaryFile(suffix=".db") as temp_db3:
        db1 = DBManager(f"sqlite:///{temp_db1.name}")
        db2 = DBManager(f"sqlite:///{temp_db1.name}")
        db3 = DBManager(f"sqlite:///{temp_db1.name}")
        are_same_instance = db1 is db2
        are_not_same_instance = db1 is not db3

    assert are_same_instance, "DBManager created more than one instance!"
    assert (
        are_not_same_instance
    ), "DBManager returned isntance with a different SQLALCHEMY_DB_URL!"
