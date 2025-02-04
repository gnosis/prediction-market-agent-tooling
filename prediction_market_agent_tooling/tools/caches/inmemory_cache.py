from functools import cache
from typing import Any, Callable, TypeVar, cast, overload

from joblib import Memory

from prediction_market_agent_tooling.config import APIKeys

MEMORY = Memory(APIKeys().CACHE_DIR, verbose=0)


T = TypeVar("T", bound=Callable[..., Any])


@overload
def persistent_inmemory_cache(
    func: None = None,
    *,
    in_memory_cache: bool = True,
) -> Callable[[T], T]:
    ...


@overload
def persistent_inmemory_cache(
    func: T,
    *,
    in_memory_cache: bool = True,
) -> T:
    ...


def persistent_inmemory_cache(
    func: T | None = None,
    *,
    in_memory_cache: bool = True,
) -> T | Callable[[T], T]:
    """
    Wraps a function with both file cache (for persistent cache) and optional in-memory cache (for speed).
    Can be used as @persistent_inmemory_cache or @persistent_inmemory_cache(in_memory_cache=False)
    """
    if func is None:
        # Ugly Pythonic way to support this decorator as `@persistent_inmemory_cache` but also `@persistent_inmemory_cache(in_memory_cache=False)`
        def decorator(func: T) -> T:
            return persistent_inmemory_cache(
                func,
                in_memory_cache=in_memory_cache,
            )

        return decorator
    else:
        # The decorator is called without arguments.
        if not APIKeys().ENABLE_CACHE:
            return func
        cached_func = MEMORY.cache(func)
        if in_memory_cache:
            cached_func = cache(cached_func)
        return cast(T, cached_func)
