import typing as t
from datetime import datetime, timedelta
from typing import Optional

import pytz
from dateutil import parser
from pydantic import GetCoreSchemaHandler
from pydantic_core import CoreSchema, core_schema
from sqlalchemy import DateTime, TypeDecorator
from sqlalchemy.engine import Dialect

from prediction_market_agent_tooling.loggers import logger


class DatetimeUTC(datetime):
    """
    As a subclass of `datetime` instead of `NewType` because otherwise it doesn't work with issubclass command which is required for SQLModel/Pydantic.
    """

    def __new__(cls, *args, **kwargs) -> "DatetimeUTC":  # type: ignore[no-untyped-def] # Pickling doesn't work if I copy-paste arguments from datetime's __new__.
        if len(args) >= 8:
            # Start of Selection
            args = args[:7] + (pytz.UTC,) + args[8:]
        else:
            kwargs["tzinfo"] = pytz.UTC
        return super().__new__(cls, *args, **kwargs)

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
        # Use union schema to handle int, str, and datetime inputs directly
        return core_schema.union_schema(
            [
                core_schema.no_info_after_validator_function(
                    cls._validate, core_schema.int_schema()
                ),
                core_schema.no_info_after_validator_function(
                    cls._validate, core_schema.str_schema()
                ),
                core_schema.no_info_after_validator_function(
                    cls._validate, handler(datetime)
                ),
            ]
        )

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
            # Divide by 1000 if the timestamp is assumed to be in milliseconds (if not, 1e11 would be year 5138).
            value = int(value / 1000) if value > 1e11 else value
            # In the past, we had bugged data where timestamp was huge and Python errored out.
            max_timestamp = int((datetime.max - timedelta(days=1)).timestamp())
            value = min(value, max_timestamp)
            value = datetime.fromtimestamp(value, tz=pytz.UTC)
        elif isinstance(value, str):
            value = parser.parse(value)
        return DatetimeUTC.from_datetime(value)

    def without_tz(self) -> datetime:
        return datetime(
            self.year,
            self.month,
            self.day,
            self.hour,
            self.minute,
            self.second,
            self.microsecond,
            tzinfo=None,
        )


class DatetimeUTCType(TypeDecorator[DatetimeUTC]):
    impl = DateTime
    cache_ok = True

    def process_bind_param(
        self, value: Optional[DatetimeUTC], dialect: Dialect
    ) -> Optional[datetime]:
        if value is None:
            return None
        # We save it consistently as UTC in the database, regardless of the database vendor,
        # but it needs to come without the tzinfo itself.
        return value.without_tz()

    def process_result_value(
        self, value: Optional[datetime], dialect: Dialect
    ) -> Optional[DatetimeUTC]:
        """Converte datetime do banco para DatetimeUTC ao carregar"""
        if value is None:
            return None
        # Database returns it in UTC, but without tzinfo.
        if value.tzinfo is None:
            value = value.replace(tzinfo=pytz.UTC)
        else:
            raise ValueError("Unexpected, it should be without tzinfo here.")
        return DatetimeUTC.from_datetime(value)
