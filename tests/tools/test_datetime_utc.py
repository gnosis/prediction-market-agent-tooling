from datetime import datetime

import pytest

from prediction_market_agent_tooling.tools.datetime_utc import DatetimeUTC


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
