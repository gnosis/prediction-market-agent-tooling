import time
from datetime import timedelta
from functools import wraps
from typing import Any, Callable, Optional, TypeVar, cast

from sqlalchemy.exc import OperationalError
from sqlmodel import Session, select

from prediction_market_agent_tooling.config import APIKeys
from prediction_market_agent_tooling.tools.cow.models import RateLimit
from prediction_market_agent_tooling.tools.datetime_utc import DatetimeUTC
from prediction_market_agent_tooling.tools.db.db_manager import DBManager
from prediction_market_agent_tooling.tools.utils import utcnow

F = TypeVar("F", bound=Callable[..., Any])

FALLBACK_SQL_ENGINE = "sqlite:///rate_limit.db"


def postgres_rate_limited(
    api_keys: APIKeys,
    rate_id: str,
    interval_seconds: float,
    shared_db: bool = False,
) -> Callable[[F], F]:
    """rate_id is used to distinguish between different rate limits for different functions"""
    limiter = RateLimiter(id=rate_id, interval_seconds=interval_seconds)

    def decorator(func: F) -> F:
        @wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            sqlalchemy_db_url = (
                api_keys.sqlalchemy_db_url.get_secret_value()
                if shared_db
                else FALLBACK_SQL_ENGINE
            )

            db_manager = DBManager(sqlalchemy_db_url)
            db_manager.create_tables([RateLimit])

            with db_manager.get_session() as session:
                limiter.enforce(session)
            return func(*args, **kwargs)

        return cast(F, wrapper)

    return decorator


class RateLimiter:
    def __init__(self, id: str, interval_seconds: float = 1.0) -> None:
        self.id = id
        self.interval = timedelta(seconds=interval_seconds)

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
            except OperationalError:
                # Backoff if DB is under contention
                elapsed_time = time.monotonic() - start_time
                if elapsed_time > timeout_seconds:
                    raise TimeoutError(
                        f"Could not acquire rate limit '{self.id}' "
                        f"after {elapsed_time:.1f} seconds due to database contention"
                    )
                time.sleep(0.5)
