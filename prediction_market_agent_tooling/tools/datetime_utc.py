import typing as t
from datetime import datetime

import pytz
from dateutil import parser
from pydantic import GetCoreSchemaHandler
from pydantic_core import CoreSchema, core_schema

from prediction_market_agent_tooling.loggers import logger


class DatetimeUTC(datetime):
    """
    As a subclass of `datetime` instead of `NewType` because otherwise it doesn't work with issubclass command which is required for SQLModel/Pydantic.
    """

    def __new__(
        cls,
        year: int,
        month: int,
        day: int,
        hour: int = 0,
        minute: int = 0,
        second: int = 0,
        microsecond: int = 0,
        tzinfo: pytz.BaseTzInfo = pytz.UTC,
        *,
        fold: int = 0,
    ) -> "DatetimeUTC":
        if tzinfo is not pytz.UTC:
            raise ValueError(f"DatetimeUTC should always be created with UTC timezone.")
        return super().__new__(
            cls,
            year=year,
            month=month,
            day=day,
            hour=hour,
            minute=minute,
            second=second,
            microsecond=microsecond,
            tzinfo=tzinfo,
            fold=fold,
        )

    @classmethod
    def _validate(cls, value: t.Any) -> "DatetimeUTC":
        if not isinstance(value, (datetime, int, str)):
            raise TypeError(
                f"Expected datetime, timestamp or string, got {type(value)}"
            )
        return cls.to_datetime_utc(value)

    @classmethod
    def __get_pydantic_core_schema__(
        cls, source_type: t.Any, handler: GetCoreSchemaHandler
    ) -> CoreSchema:
        dt_schema = handler(datetime)
        return core_schema.no_info_after_validator_function(cls._validate, dt_schema)

    @staticmethod
    def from_datetime(dt: datetime) -> "DatetimeUTC":
        """
        Converts a datetime object to DatetimeUTC, ensuring it is timezone-aware in UTC.
        """
        if dt.tzinfo is None:
            logger.warning(
                f"tzinfo not provided, assuming the timezone of {dt=} is UTC."
            )
            dt = dt.replace(tzinfo=pytz.UTC)
        else:
            dt = dt.astimezone(pytz.UTC)
        return DatetimeUTC(
            dt.year,
            dt.month,
            dt.day,
            dt.hour,
            dt.minute,
            dt.second,
            dt.microsecond,
            tzinfo=pytz.UTC,
        )

    @staticmethod
    def to_datetime_utc(value: datetime | int | str) -> "DatetimeUTC":
        if isinstance(value, int):
            # Divide by 1000 if the timestamp is assumed to be in miliseconds (if not, 1e11 would be year 5138).
            value = int(value / 1000) if value > 1e11 else value
            value = datetime.fromtimestamp(value, tz=pytz.UTC)
        elif isinstance(value, str):
            value = parser.parse(value)
        return DatetimeUTC.from_datetime(value)
