import pickle
from datetime import datetime, timedelta

import pytest
import pytz

from prediction_market_agent_tooling.tools.datetime_utc import DatetimeUTC
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
