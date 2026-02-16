import pickle
from datetime import datetime, timedelta
from typing import Optional

import pytest
import pytz
from sqlalchemy import Engine
from sqlmodel import Field, Session, SQLModel, create_engine, select

from prediction_market_agent_tooling.tools.datetime_utc import (
    DatetimeUTC,
    DatetimeUTCType,
)
from prediction_market_agent_tooling.tools.utils import utcnow


@pytest.mark.parametrize(
    "value, expected",
    [
        ("2024-10-10", DatetimeUTC(2024, 10, 10)),
        ("2024-10-10T17:00+02:00", DatetimeUTC(2024, 10, 10, 15)),
        ("2003 Sep 25", DatetimeUTC(2003, 9, 25)),
        (
            1727879129,
            DatetimeUTC(
                2024,
                10,
                2,
                14,
                25,
                29,
            ),
        ),
    ],
)
def test_datetime_utc(value: str | int | datetime, expected: DatetimeUTC) -> None:
    assert DatetimeUTC.to_datetime_utc(value) == expected


def test_datetime_utc_pickle() -> None:
    now = utcnow()
    dumped = pickle.dumps(now)
    loaded = pickle.loads(dumped)
    assert now == loaded


def test_datetime_utc_is_utc() -> None:
    now = utcnow()
    assert isinstance(now, DatetimeUTC)
    assert now.tzinfo == pytz.UTC


def test_datetime_utc_with_timedelta() -> None:
    now = utcnow()
    then = now + timedelta(hours=12)
    assert then > now
    assert type(now) == type(then)
    assert isinstance(then, DatetimeUTC)


class TestModelWithDatetimeUTC(SQLModel, table=True):
    """Test model using DatetimeUTC with SQLModel."""

    __tablename__ = "test_datetime_utc"

    id: Optional[int] = Field(default=None, primary_key=True)
    created_at: DatetimeUTC = Field(sa_type=DatetimeUTCType)
    updated_at: Optional[DatetimeUTC] = Field(default=None, sa_type=DatetimeUTCType)
    # Without sa_type, it will come back as a normal datetime!
    not_typed_correctly: DatetimeUTC


@pytest.fixture
def sqlite_engine() -> Engine:
    """Create an in-memory SQLite engine for testing."""
    engine = create_engine("sqlite:///:memory:")
    SQLModel.metadata.create_all(engine)
    return engine


def test_datetime_utc_sqlmodel_save_and_load(sqlite_engine: Engine) -> None:
    """Test that DatetimeUTC is correctly saved and loaded from SQLModel."""
    now = utcnow()

    # Create and save a record
    with Session(sqlite_engine) as session:
        record = TestModelWithDatetimeUTC(created_at=now, not_typed_correctly=now)
        session.add(record)
        session.commit()
        record_id = record.id

    # Load the record in a new session
    with Session(sqlite_engine) as session:
        loaded = session.get(TestModelWithDatetimeUTC, record_id)
        assert loaded is not None
        assert loaded.created_at == now
        assert isinstance(loaded.created_at, DatetimeUTC)
        assert loaded.created_at.tzinfo == pytz.UTC
        assert isinstance(loaded.not_typed_correctly, datetime)


def test_datetime_utc_sqlmodel_with_none(sqlite_engine: Engine) -> None:
    """Test that None values are correctly handled."""
    now = utcnow()

    with Session(sqlite_engine) as session:
        record = TestModelWithDatetimeUTC(
            created_at=now, updated_at=None, not_typed_correctly=now
        )
        session.add(record)
        session.commit()
        record_id = record.id

    with Session(sqlite_engine) as session:
        loaded = session.get(TestModelWithDatetimeUTC, record_id)
        assert loaded is not None
        assert loaded.updated_at is None
        assert isinstance(loaded.created_at, DatetimeUTC)
        assert isinstance(loaded.not_typed_correctly, datetime)


def test_datetime_utc_sqlmodel_query_filter(sqlite_engine: Engine) -> None:
    """Test that DatetimeUTC works correctly in query filters."""
    now = utcnow()
    earlier = now - timedelta(hours=1)
    later = now + timedelta(hours=1)

    with Session(sqlite_engine) as session:
        record = TestModelWithDatetimeUTC(created_at=now, not_typed_correctly=now)
        session.add(record)
        session.commit()

    with Session(sqlite_engine) as session:
        # Query with filter - should find the record
        results = session.exec(
            select(TestModelWithDatetimeUTC).where(
                TestModelWithDatetimeUTC.created_at > earlier
            )
        ).all()
        assert len(results) == 1

        # Query with filter - should not find the record
        results = session.exec(
            select(TestModelWithDatetimeUTC).where(
                TestModelWithDatetimeUTC.created_at > later
            )
        ).all()
        assert len(results) == 0


def test_datetime_utc_sqlmodel_update(sqlite_engine: Engine) -> None:
    """Test that DatetimeUTC fields can be updated correctly."""
    now = utcnow()
    later = now + timedelta(hours=1)

    with Session(sqlite_engine) as session:
        record = TestModelWithDatetimeUTC(created_at=now, not_typed_correctly=now)
        session.add(record)
        session.commit()
        record_id = record.id

    with Session(sqlite_engine) as session:
        loaded = session.get(TestModelWithDatetimeUTC, record_id)
        assert loaded is not None
        loaded.updated_at = later
        session.add(loaded)
        session.commit()

    with Session(sqlite_engine) as session:
        loaded = session.get(TestModelWithDatetimeUTC, record_id)
        assert loaded is not None
        assert loaded.updated_at == later
        assert isinstance(loaded.updated_at, DatetimeUTC)
        assert loaded.updated_at.tzinfo == pytz.UTC
        assert isinstance(loaded.not_typed_correctly, datetime)


def test_datetime_utc_sqlmodel_preserves_microseconds(sqlite_engine: Engine) -> None:
    """Test that microseconds are preserved when saving and loading."""
    dt = DatetimeUTC(2024, 10, 15, 12, 30, 45, 123456)

    with Session(sqlite_engine) as session:
        record = TestModelWithDatetimeUTC(created_at=dt, not_typed_correctly=dt)
        session.add(record)
        session.commit()
        record_id = record.id

    with Session(sqlite_engine) as session:
        loaded = session.get(TestModelWithDatetimeUTC, record_id)
        assert loaded is not None
        assert loaded.created_at.microsecond == 123456
        assert loaded.created_at == dt
        assert isinstance(loaded.created_at, DatetimeUTC)
        assert isinstance(loaded.not_typed_correctly, datetime)
