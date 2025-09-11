import hashlib
import inspect
import json
from datetime import timedelta
from functools import wraps
from types import UnionType
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

import psycopg2
from pydantic import BaseModel
from sqlalchemy import Column
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.exc import DataError
from sqlmodel import Field, SQLModel, desc, select

from prediction_market_agent_tooling.config import APIKeys
from prediction_market_agent_tooling.loggers import logger
from prediction_market_agent_tooling.tools.datetime_utc import DatetimeUTC
from prediction_market_agent_tooling.tools.db.db_manager import DBManager
from prediction_market_agent_tooling.tools.utils import utcnow

DB_CACHE_LOG_PREFIX = "[db-cache]"

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
    log_error_on_unsavable_data: bool = True,
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
    log_error_on_unsavable_data: bool = True,
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
    log_error_on_unsavable_data: bool = True,
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
                log_error_on_unsavable_data=log_error_on_unsavable_data,
            )

        return decorator

    api_keys = api_keys if api_keys is not None else APIKeys()
    
    # Check if the decorated function is async
    if inspect.iscoroutinefunction(func):
        @wraps(func)
        async def wrapper(*args: Any, **kwargs: Any) -> Any:
            # If caching is disabled, just call the function and return it
            if not api_keys.ENABLE_CACHE:
                return await func(*args, **kwargs)

            DBManager(api_keys.sqlalchemy_db_url.get_secret_value()).create_tables(
                [FunctionCache]
            )

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
            is_pydantic_model = return_type is not None and contains_pydantic_model(
                return_type
            )

            with DBManager(
                api_keys.sqlalchemy_db_url.get_secret_value()
            ).get_session() as session:
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

            if cached_result:
                logger.info(
                    # Keep the special [case-hit] identifier so we can easily track it in GCP.
                    f"{DB_CACHE_LOG_PREFIX} [cache-hit] Cache hit for {full_function_name} with args {args_dict} and output {cached_result.result}"
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
                            f"{DB_CACHE_LOG_PREFIX} [cache-miss] Can not validate {cached_result=} into {return_type=} because {e=}, treating as cache miss."
                        )
                        cached_result = None
                else:
                    return cached_result.result

            # On cache miss, compute the result - AWAIT for async
            computed_result = await func(*args, **kwargs)
            # Keep the special [case-miss] identifier so we can easily track it in GCP.
            logger.info(
                f"{DB_CACHE_LOG_PREFIX} [cache-miss] Cache miss for {full_function_name} with args {args_dict}, computed the output {computed_result}"
            )

            # If postgres access was specified, save it.
            if cache_none or computed_result is not None:
                cache_entry = FunctionCache(
                    function_name=function_name,
                    full_function_name=full_function_name,
                    args_hash=args_hash,
                    args=args_dict,
                    result=computed_result,
                    created_at=utcnow(),
                )
                # Do not raise an exception if saving to the database fails, just log it and let the agent continue the work.
                try:
                    with DBManager(
                        api_keys.sqlalchemy_db_url.get_secret_value()
                    ).get_session() as session:
                        logger.info(
                            f"{DB_CACHE_LOG_PREFIX} [cache-info] Saving {cache_entry} into database."
                        )
                        session.add(cache_entry)
                        session.commit()
                except (DataError, psycopg2.errors.UntranslatableCharacter) as e:
                    (logger.error if log_error_on_unsavable_data else logger.warning)(
                        f"{DB_CACHE_LOG_PREFIX} [cache-error] Failed to save {cache_entry} into database, ignoring, because: {e}"
                    )
                except Exception:
                    logger.exception(
                        f"{DB_CACHE_LOG_PREFIX} [cache-error] Failed to save {cache_entry} into database, ignoring."
                    )

            return computed_result
        
        return cast(FunctionT, wrapper)

    @wraps(func)
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        # If caching is disabled, just call the function and return it
        if not api_keys.ENABLE_CACHE:
            return func(*args, **kwargs)

        DBManager(api_keys.sqlalchemy_db_url.get_secret_value()).create_tables(
            [FunctionCache]
        )

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
        is_pydantic_model = return_type is not None and contains_pydantic_model(
            return_type
        )

        with DBManager(
            api_keys.sqlalchemy_db_url.get_secret_value()
        ).get_session() as session:
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

        if cached_result:
            logger.info(
                # Keep the special [case-hit] identifier so we can easily track it in GCP.
                f"{DB_CACHE_LOG_PREFIX} [cache-hit] Cache hit for {full_function_name} with args {args_dict} and output {cached_result.result}"
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
                        f"{DB_CACHE_LOG_PREFIX} [cache-miss] Can not validate {cached_result=} into {return_type=} because {e=}, treating as cache miss."
                    )
                    cached_result = None
            else:
                return cached_result.result

        # On cache miss, compute the result
        computed_result = func(*args, **kwargs)
        # Keep the special [case-miss] identifier so we can easily track it in GCP.
        logger.info(
            f"{DB_CACHE_LOG_PREFIX} [cache-miss] Cache miss for {full_function_name} with args {args_dict}, computed the output {computed_result}"
        )

        # If postgres access was specified, save it.
        if cache_none or computed_result is not None:
            cache_entry = FunctionCache(
                function_name=function_name,
                full_function_name=full_function_name,
                args_hash=args_hash,
                args=args_dict,
                result=computed_result,
                created_at=utcnow(),
            )
            # Do not raise an exception if saving to the database fails, just log it and let the agent continue the work.
            try:
                with DBManager(
                    api_keys.sqlalchemy_db_url.get_secret_value()
                ).get_session() as session:
                    logger.info(
                        f"{DB_CACHE_LOG_PREFIX} [cache-info] Saving {cache_entry} into database."
                    )
                    session.add(cache_entry)
                    session.commit()
            except (DataError, psycopg2.errors.UntranslatableCharacter) as e:
                (logger.error if log_error_on_unsavable_data else logger.warning)(
                    f"{DB_CACHE_LOG_PREFIX} [cache-error] Failed to save {cache_entry} into database, ignoring, because: {e}"
                )
            except Exception:
                logger.exception(
                    f"{DB_CACHE_LOG_PREFIX} [cache-error] Failed to save {cache_entry} into database, ignoring."
                )

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
        # If the origin is a union and one of the unions is basemodel, convert it to it.
        elif (
            origin is UnionType
            and (
                base_model_from_args := next(
                    (x for x in args if issubclass(x, BaseModel)), None
                )
            )
            is not None
        ):
            return base_model_from_args.model_validate(data)
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
