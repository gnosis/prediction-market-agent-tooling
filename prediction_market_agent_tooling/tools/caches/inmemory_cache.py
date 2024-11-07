from functools import cache
from typing import Any, Callable, TypeVar, cast

from joblib import Memory

from prediction_market_agent_tooling.config import APIKeys

MEMORY = Memory(APIKeys().CACHE_DIR, verbose=0)

T = TypeVar("T", bound=Callable[..., Any])


def persistent_inmemory_cache(func: T) -> T:
    """
    Wraps a function with both file cache (for persistent cache) and in-memory cache (for speed).
    """
    return cast(T, cache(MEMORY.cache(func)) if APIKeys().ENABLE_CACHE else func)
