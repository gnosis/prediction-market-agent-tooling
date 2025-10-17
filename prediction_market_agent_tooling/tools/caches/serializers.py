import json
import typing as t
from datetime import date, timedelta

from pydantic import BaseModel

from prediction_market_agent_tooling.gtypes import HexBytes
from prediction_market_agent_tooling.tools.datetime_utc import DatetimeUTC


def json_serializer(x: t.Any) -> str:
    return json.dumps(x, default=json_serializer_default_fn)


def json_serializer_default_fn(
    y: DatetimeUTC | timedelta | date | HexBytes | BaseModel,
) -> str | dict[str, t.Any]:
    """
    Used to serialize objects that don't support it by default into a specific string that can be deserialized out later.
    If this function returns a dictionary, it will be called recursively.
    If you add something here, also add it to `replace_custom_stringified_objects` below.
    """
    if isinstance(y, DatetimeUTC):
        return f"DatetimeUTC::{y.isoformat()}"
    elif isinstance(y, timedelta):
        return f"timedelta::{y.total_seconds()}"
    elif isinstance(y, date):
        return f"date::{y.isoformat()}"
    elif isinstance(y, HexBytes):
        return f"HexBytes::{y.to_0x_hex()}"
    elif isinstance(y, BaseModel):
        return y.model_dump()
    raise TypeError(
        f"Unsupported type for the default json serialize function, value is {y}."
    )


def json_deserializer(s: str) -> t.Any:
    data = json.loads(s)
    return replace_custom_stringified_objects(data)


def replace_custom_stringified_objects(obj: t.Any) -> t.Any:
    """
    Used to deserialize objects from `json_serializer_default_fn` into their proper form.
    """
    if isinstance(obj, str):
        if obj.startswith("DatetimeUTC::"):
            iso_str = obj[len("DatetimeUTC::") :]
            return DatetimeUTC.to_datetime_utc(iso_str)
        elif obj.startswith("timedelta::"):
            total_seconds_str = obj[len("timedelta::") :]
            return timedelta(seconds=float(total_seconds_str))
        elif obj.startswith("date::"):
            iso_str = obj[len("date::") :]
            return date.fromisoformat(iso_str)
        elif obj.startswith("HexBytes::"):
            hex_str = obj[len("HexBytes::") :]
            return HexBytes(hex_str)
        else:
            return obj
    elif isinstance(obj, dict):
        return {k: replace_custom_stringified_objects(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [replace_custom_stringified_objects(item) for item in obj]
    else:
        return obj
