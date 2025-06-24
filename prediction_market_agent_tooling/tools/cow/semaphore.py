import time
from datetime import timedelta
from functools import wraps
from typing import Any, Callable, Optional, TypeVar, cast

from sqlalchemy.exc import OperationalError
from sqlmodel import Session, select

from prediction_market_agent_tooling.config import APIKeys
from prediction_market_agent_tooling.tools.cow.models import RateLimit
from prediction_market_agent_tooling.tools.db.db_manager import DBManager
from prediction_market_agent_tooling.tools.utils import utcnow

F = TypeVar("F", bound=Callable[..., Any])


def postgres_rate_limited(
    api_keys: APIKeys, rate_id: str = "default", interval_seconds: float = 1.0
) -> Callable[[F], F]:
    """rate_id is used to distinguish between different rate limits for different functions"""
    limiter = RateLimiter(id=rate_id, interval_seconds=interval_seconds)

    def decorator(func: F) -> F:
        @wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            DBManager(api_keys.sqlalchemy_db_url.get_secret_value()).create_tables(
                [RateLimit]
            )

            with DBManager(
                api_keys.sqlalchemy_db_url.get_secret_value()
            ).get_session() as session:
                limiter.enforce(session)
            return func(*args, **kwargs)

        return cast(F, wrapper)

    return decorator


class RateLimiter:
    def __init__(self, id: str, interval_seconds: float = 1.0) -> None:
        self.id = id
        self.interval = timedelta(seconds=interval_seconds)

    def enforce(self, session: Session) -> None:
        """
        Enforces the rate limit inside a transaction.
        Blocks until allowed.
        """
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
                        session.add(RateLimit(id=self.id, last_called_at=utcnow()))
                        return

                    elapsed = now - result.last_called_at
                    if elapsed >= self.interval:
                        result.last_called_at = now
                        session.add(result)
                        return

                    # Not enough time passed, sleep and retry
                    to_sleep = (self.interval - elapsed).total_seconds()
                time.sleep(to_sleep)
            except OperationalError:
                # Backoff if DB is under contention
                time.sleep(0.1)
