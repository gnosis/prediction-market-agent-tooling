import asyncio
import inspect
import time
from datetime import timedelta
from functools import wraps
from typing import Any, Callable, Optional, TypeVar, cast

from pydantic import SecretStr
from sqlalchemy.exc import OperationalError
from sqlmodel import Session, select

from prediction_market_agent_tooling.config import APIKeys
from prediction_market_agent_tooling.tools.cow.models import RateLimit
from prediction_market_agent_tooling.tools.datetime_utc import DatetimeUTC
from prediction_market_agent_tooling.tools.db.db_manager import (
    DBManager,
    EnsureTableManager,
)
from prediction_market_agent_tooling.tools.utils import utcnow

F = TypeVar("F", bound=Callable[..., Any])

FALLBACK_SQL_ENGINE = SecretStr("sqlite:///rate_limit.db")

_table_manager = EnsureTableManager([RateLimit])


def postgres_rate_limited(
    api_keys: APIKeys,
    rate_id: str,
    interval_seconds: float,
    shared_db: bool = False,
) -> Callable[[F], F]:
    """
    Rate limiter decorator that works with both sync and async functions.

    rate_id is used to distinguish between different rate limits for different functions.

    For async functions, uses AsyncRateLimiter with semaphore to prevent multiple
    async tasks from competing for the database lock simultaneously, while still
    maintaining cross-process rate limits via PostgreSQL.

    For sync functions, uses database-backed RateLimiter for proper synchronization.
    """
    limiter = RateLimiter(id=rate_id, interval_seconds=interval_seconds)

    def decorator(func: F) -> F:
        if inspect.iscoroutinefunction(func):
            # Get or create async rate limiter for this rate_id
            async_limiter = AsyncRateLimiter.get_instance(
                id=rate_id, interval_seconds=interval_seconds
            )

            # Async function wrapper using hybrid rate limiter
            @wraps(func)
            async def async_wrapper(*args: Any, **kwargs: Any) -> Any:
                sqlalchemy_db_url = (
                    api_keys.sqlalchemy_db_url if shared_db else FALLBACK_SQL_ENGINE
                )
                await _table_manager.ensure_tables_async(sqlalchemy_db_url)

                db_manager = DBManager(sqlalchemy_db_url.get_secret_value())
                await async_limiter.enforce(db_manager)
                return await func(*args, **kwargs)

            return cast(F, async_wrapper)

        else:
            # Sync function wrapper using database-backed rate limiter
            @wraps(func)
            def sync_wrapper(*args: Any, **kwargs: Any) -> Any:
                sqlalchemy_db_url = (
                    api_keys.sqlalchemy_db_url if shared_db else FALLBACK_SQL_ENGINE
                )
                _table_manager.ensure_tables_sync(sqlalchemy_db_url)

                db_manager = DBManager(sqlalchemy_db_url.get_secret_value())
                limiter.enforce_sync(db_manager)
                return func(*args, **kwargs)

            return cast(F, sync_wrapper)

    return decorator


class AsyncRateLimiter:
    """
    Hybrid async rate limiter that combines in-process coordination with database-based
    cross-process rate limiting.

    This prevents multiple async tasks in the same process from competing for the
    database lock simultaneously, while still maintaining rate limits across different
    deployments/processes via the PostgreSQL-based RateLimiter.

    Uses a class-level dictionary to maintain singleton instances per rate_id.
    """

    _instances: dict[str, "AsyncRateLimiter"] = {}

    def __init__(
        self,
        id: str,
        interval_seconds: float,
    ):
        self.id = id
        self.interval_seconds = interval_seconds
        # In-process semaphore to allow only one async task to access DB at a time
        self._semaphore = asyncio.Semaphore(1)

    @classmethod
    def get_instance(cls, id: str, interval_seconds: float) -> "AsyncRateLimiter":
        """
        Get or create an AsyncRateLimiter instance for the given rate_id.

        This ensures that the same rate limiter instance is used across multiple
        calls with the same rate_id, maintaining proper in-process coordination.

        Args:
            id: The unique identifier for this rate limiter
            interval_seconds: The minimum interval between rate-limited calls

        Returns:
            The singleton AsyncRateLimiter instance for this rate_id
        """
        if id not in cls._instances:
            cls._instances[id] = cls(id=id, interval_seconds=interval_seconds)
        return cls._instances[id]

    async def enforce(
        self, db_manager: DBManager, timeout_seconds: float = 30.0
    ) -> None:
        """
        Enforce rate limiting in async context using a hybrid approach:
        1. Use semaphore to ensure only one async task accesses database at a time
        2. Then check database for cross-process rate limiting

        This prevents multiple async tasks from competing for the database lock
        simultaneously, while still maintaining rate limits across different
        deployments via the PostgreSQL-based RateLimiter.

        Args:
            db_manager: The database manager to use for getting sessions
            timeout_seconds: Maximum time in seconds to wait before giving up

        Raises:
            TimeoutError: If the rate limit cannot be acquired within timeout
        """
        # Step 1: Acquire semaphore to serialize database access within this process
        async with self._semaphore:
            # Step 2: Check database for cross-process rate limiting
            sync_limiter = RateLimiter(
                id=self.id, interval_seconds=self.interval_seconds
            )
            await asyncio.to_thread(
                lambda: sync_limiter.enforce_sync(db_manager, timeout_seconds)
            )


class RateLimiter:
    def __init__(self, id: str, interval_seconds: float = 1.0) -> None:
        self.id = id
        self.interval = timedelta(seconds=interval_seconds)

    def enforce_sync(
        self, db_manager: DBManager, timeout_seconds: float = 30.0
    ) -> None:
        """
        Enforces the rate limit inside a transaction using a DBManager.
        Blocks until allowed or timeout is reached.

        Args:
            db_manager: The database manager to use for getting sessions
            timeout_seconds: Maximum time in seconds to wait before giving up

        Raises:
            TimeoutError: If the rate limit cannot be acquired within the timeout period
        """
        with db_manager.get_session() as session:
            self.enforce(session, timeout_seconds)

    def enforce(self, session: Session, timeout_seconds: float = 30.0) -> None:
        """
        Enforces the rate limit inside a transaction.
        Blocks until allowed or timeout is reached.

        Args:
            session: The database session to use
            timeout_seconds: Maximum time in seconds to wait before giving up

        Raises:
            TimeoutError: If the rate limit cannot be acquired within the timeout period
        """
        start_time = time.monotonic()

        while True:
            try:
                with session.begin():
                    stmt = (
                        select(RateLimit)
                        .where(RateLimit.id == self.id)
                        .with_for_update()
                    )
                    result: Optional[RateLimit] = session.exec(stmt).first()

                    now = utcnow()

                    if result is None:
                        # First time this limiter is used
                        session.add(RateLimit(id=self.id))
                        return

                    last_called_aware = DatetimeUTC.from_datetime(result.last_called_at)
                    elapsed = now - last_called_aware
                    if elapsed >= self.interval:
                        result.last_called_at = now
                        session.add(result)
                        return

                    # Not enough time passed, sleep and retry
                    to_sleep = (self.interval - elapsed).total_seconds()
                    time.sleep(to_sleep)
            except OperationalError as e:
                # Backoff if DB is under contention
                elapsed_time = time.monotonic() - start_time
                if elapsed_time > timeout_seconds:
                    raise TimeoutError(
                        f"Could not acquire rate limit '{self.id}' "
                        f"after {elapsed_time:.1f} seconds due to database error: {e}"
                    )
                time.sleep(0.5)
