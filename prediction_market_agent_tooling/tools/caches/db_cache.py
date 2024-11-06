import hashlib
import inspect
import json
from datetime import date, timedelta
from functools import wraps
from typing import (
    Any,
    Callable,
    Sequence,
    TypeVar,
    cast,
    get_args,
    get_origin,
    overload,
)

from pydantic import BaseModel
from sqlalchemy import Column
from sqlalchemy.dialects.postgresql import JSONB
from sqlmodel import Field, Session, SQLModel, create_engine, desc, select

from prediction_market_agent_tooling.config import APIKeys
from prediction_market_agent_tooling.loggers import logger
from prediction_market_agent_tooling.tools.datetime_utc import DatetimeUTC
from prediction_market_agent_tooling.tools.utils import utcnow

FunctionT = TypeVar("FunctionT", bound=Callable[..., Any])


class FunctionCache(SQLModel, table=True):
    __tablename__ = "function_cache"
    id: int | None = Field(default=None, primary_key=True)
    function_name: str = Field(index=True)
    full_function_name: str = Field(index=True)
    # Args are stored to see what was the function called with.
    args: Any = Field(sa_column=Column(JSONB, nullable=False))
    # Args hash is stored as a fast look-up option when looking for cache hits.
    args_hash: str = Field(index=True)
    result: Any = Field(sa_column=Column(JSONB, nullable=False))
    created_at: DatetimeUTC = Field(default_factory=utcnow, index=True)


@overload
def db_cache(
    func: None = None,
    *,
    max_age: timedelta | None = None,
    cache_none: bool = True,
    api_keys: APIKeys | None = None,
    ignore_args: Sequence[str] | None = None,
    ignore_arg_types: Sequence[type] | None = None,
) -> Callable[[FunctionT], FunctionT]:
    ...


@overload
def db_cache(
    func: FunctionT,
    *,
    max_age: timedelta | None = None,
    cache_none: bool = True,
    api_keys: APIKeys | None = None,
    ignore_args: Sequence[str] | None = None,
    ignore_arg_types: Sequence[type] | None = None,
) -> FunctionT:
    ...


def db_cache(
    func: FunctionT | None = None,
    *,
    max_age: timedelta | None = None,
    cache_none: bool = True,
    api_keys: APIKeys | None = None,
    ignore_args: Sequence[str] | None = None,
    ignore_arg_types: Sequence[type] | None = None,
) -> FunctionT | Callable[[FunctionT], FunctionT]:
    if func is None:
        # Ugly Pythonic way to support this decorator as `@postgres_cache` but also `@postgres_cache(max_age=timedelta(days=3))`
        def decorator(func: FunctionT) -> FunctionT:
            return db_cache(
                func,
                max_age=max_age,
                cache_none=cache_none,
                api_keys=api_keys,
                ignore_args=ignore_args,
                ignore_arg_types=ignore_arg_types,
            )

        return decorator

    api_keys = api_keys if api_keys is not None else APIKeys()

    sqlalchemy_db_url = api_keys.SQLALCHEMY_DB_URL
    if sqlalchemy_db_url is None:
        logger.warning(
            f"SQLALCHEMY_DB_URL not provided in the environment, skipping function caching."
        )

    engine = (
        create_engine(
            sqlalchemy_db_url.get_secret_value(),
            # Use custom json serializer and deserializer, because otherwise, for example `datetime` serialization would fail.
            json_serializer=json_serializer,
            json_deserializer=json_deserializer,
        )
        if sqlalchemy_db_url is not None
        else None
    )

    # Create table if it doesn't exist
    if engine is not None:
        SQLModel.metadata.create_all(engine)

    @wraps(func)
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        # If caching is disabled, just call the function and return it
        if not api_keys.ENABLE_CACHE:
            return func(*args, **kwargs)

        # Convert *args and **kwargs to a single dictionary, where we have names for arguments passed as args as well.
        signature = inspect.signature(func)
        bound_arguments = signature.bind(*args, **kwargs)
        bound_arguments.apply_defaults()

        # Convert any argument that is Pydantic model into classic dictionary, otherwise it won't be json-serializable.
        args_dict: dict[str, Any] = bound_arguments.arguments

        # Remove `self` or `cls` if present (in case of class' methods)
        if "self" in args_dict:
            del args_dict["self"]
        if "cls" in args_dict:
            del args_dict["cls"]

        # Remove ignored arguments
        if ignore_args:
            for arg in ignore_args:
                if arg in args_dict:
                    del args_dict[arg]

        # Remove arguments of ignored types
        if ignore_arg_types:
            args_dict = {
                k: v
                for k, v in args_dict.items()
                if not isinstance(v, tuple(ignore_arg_types))
            }

        # Compute a hash of the function arguments used for lookup of cached results
        arg_string = json.dumps(args_dict, sort_keys=True, default=str)
        args_hash = hashlib.md5(arg_string.encode()).hexdigest()

        # Get the full function name as concat of module and qualname, to not accidentally clash
        full_function_name = func.__module__ + "." + func.__qualname__
        # But also get the standard function name to easily search for it in database
        function_name = func.__name__

        # Determine if the function returns or contains Pydantic BaseModel(s)
        return_type = func.__annotations__.get("return", None)
        is_pydantic_model = False

        if return_type is not None and contains_pydantic_model(return_type):
            is_pydantic_model = True

        # If postgres access was specified, try to find a hit
        if engine is not None:
            with Session(engine) as session:
                # Try to get cached result
                statement = (
                    select(FunctionCache)
                    .where(
                        FunctionCache.function_name == function_name,
                        FunctionCache.full_function_name == full_function_name,
                        FunctionCache.args_hash == args_hash,
                    )
                    .order_by(desc(FunctionCache.created_at))
                )
                if max_age is not None:
                    cutoff_time = utcnow() - max_age
                    statement = statement.where(FunctionCache.created_at >= cutoff_time)
                cached_result = session.exec(statement).first()
        else:
            cached_result = None

        if cached_result:
            logger.info(
                # Keep the special [case-hit] identifier so we can easily track it in GCP.
                f"[cache-hit] Cache hit for {full_function_name} with args {args_dict} and output {cached_result.result}"
            )
            if is_pydantic_model:
                # If the output contains any Pydantic models, we need to initialise them.
                try:
                    return convert_cached_output_to_pydantic(
                        return_type, cached_result.result
                    )
                except ValueError as e:
                    # In case of backward-incompatible pydantic model, just treat it as cache miss, to not error out.
                    logger.warning(
                        f"Can not validate {cached_result=} into {return_type=} because {e=}, treating as cache miss."
                    )
                    cached_result = None
            else:
                return cached_result.result

        # On cache miss, compute the result
        computed_result = func(*args, **kwargs)
        # Keep the special [case-miss] identifier so we can easily track it in GCP.
        logger.info(
            f"[cache-miss] Cache miss for {full_function_name} with args {args_dict}, computed the output {computed_result}"
        )

        # If postgres access was specified, save it.
        if engine is not None and (cache_none or computed_result is not None):
            cache_entry = FunctionCache(
                function_name=function_name,
                full_function_name=full_function_name,
                args_hash=args_hash,
                args=args_dict,
                result=computed_result,
                created_at=utcnow(),
            )
            with Session(engine) as session:
                logger.info(f"Saving {cache_entry} into database.")
                session.add(cache_entry)
                session.commit()

        return computed_result

    return cast(FunctionT, wrapper)


def contains_pydantic_model(return_type: Any) -> bool:
    """
    Check if the return type contains anything that's a Pydantic model (including nested structures, like `list[BaseModel]`, `dict[str, list[BaseModel]]`, etc.)
    """
    if return_type is None:
        return False
    origin = get_origin(return_type)
    if origin is not None:
        return any(contains_pydantic_model(arg) for arg in get_args(return_type))
    if inspect.isclass(return_type):
        return issubclass(return_type, BaseModel)
    return False


def json_serializer_default_fn(
    y: DatetimeUTC | timedelta | date | BaseModel,
) -> str | dict[str, Any]:
    """
    Used to serialize objects that don't support it by default into a specific string that can be deserialized out later.
    If this function returns a dictionary, it will be called recursivelly.
    If you add something here, also add it to `replace_custom_stringified_objects` below.
    """
    if isinstance(y, DatetimeUTC):
        return f"DatetimeUTC::{y.isoformat()}"
    elif isinstance(y, timedelta):
        return f"timedelta::{y.total_seconds()}"
    elif isinstance(y, date):
        return f"date::{y.isoformat()}"
    elif isinstance(y, BaseModel):
        return y.model_dump()
    raise TypeError(
        f"Unsuported type for the default json serialize function, value is {y}."
    )


def json_serializer(x: Any) -> str:
    return json.dumps(x, default=json_serializer_default_fn)


def replace_custom_stringified_objects(obj: Any) -> Any:
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
        else:
            return obj
    elif isinstance(obj, dict):
        return {k: replace_custom_stringified_objects(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [replace_custom_stringified_objects(item) for item in obj]
    else:
        return obj


def json_deserializer(s: str) -> Any:
    data = json.loads(s)
    return replace_custom_stringified_objects(data)


def convert_cached_output_to_pydantic(return_type: Any, data: Any) -> Any:
    """
    Used to initialize Pydantic models from anything cached that was originally a Pydantic model in the output. Including models in nested structures.
    """
    # Get the origin and arguments of the model type
    origin = get_origin(return_type)
    args = get_args(return_type)

    # Check if the data is a dictionary
    if isinstance(data, dict):
        # If the model has no origin, check if it is a subclass of BaseModel
        if origin is None:
            if inspect.isclass(return_type) and issubclass(return_type, BaseModel):
                # Convert the dictionary to a Pydantic model
                return return_type(
                    **{
                        k: convert_cached_output_to_pydantic(
                            getattr(return_type, k, None), v
                        )
                        for k, v in data.items()
                    }
                )
            else:
                # If not a Pydantic model, return the data as is
                return data
        # If the origin is a dictionary, convert keys and values
        elif origin is dict:
            key_type, value_type = args
            return {
                convert_cached_output_to_pydantic(
                    key_type, k
                ): convert_cached_output_to_pydantic(value_type, v)
                for k, v in data.items()
            }
        else:
            # If the origin is not a dictionary, return the data as is
            return data
    # Check if the data is a list
    elif isinstance(data, (list, tuple)):
        # If the origin is a list or tuple, convert each item
        if origin in {list, tuple}:
            item_type = args[0]
            converted_items = [
                convert_cached_output_to_pydantic(item_type, item) for item in data
            ]
            return type(data)(converted_items)
        else:
            # If the origin is not a list or tuple, return the data as is
            return data
    else:
        # If the data is neither a dictionary nor a list, return it as is
        return data
