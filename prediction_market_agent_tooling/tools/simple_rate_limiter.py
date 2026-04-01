import asyncio
import threading
import time


class SimpleRateLimiter:
    """
    Simple rate limiter that ensures at most `max_per_second` calls per second.

    Use `postgres_rate_limited` from PMAT if you need it to be synced across pods as well.
    """

    def __init__(self, max_per_second: int) -> None:
        self.max_per_second = max_per_second
        self.timestamps: list[float] = []
        self._lock = asyncio.Lock()

    async def acquire(self) -> None:
        async with self._lock:
            now = time.monotonic()
            # Remove timestamps older than 1 second
            self.timestamps = [t for t in self.timestamps if now - t < 1.0]

            if len(self.timestamps) >= self.max_per_second:
                # Wait until the oldest timestamp is more than 1 second old
                sleep_time = 1.0 - (now - self.timestamps[0])
                if sleep_time > 0:
                    await asyncio.sleep(sleep_time)
                    # Clean up again after sleeping
                    now = time.monotonic()
                    self.timestamps = [t for t in self.timestamps if now - t < 1.0]

            self.timestamps.append(time.monotonic())


class SimpleSyncRateLimiter:
    """
    Simple synchronous rate limiter that ensures at most `max_per_second` calls per second.

    Use `postgres_rate_limited` from PMAT if you need it to be synced across pods as well.
    """

    def __init__(self, max_per_second: int) -> None:
        self.max_per_second = max_per_second
        self.timestamps: list[float] = []
        self._lock = threading.Lock()

    def acquire(self) -> None:
        with self._lock:
            now = time.monotonic()
            # Remove timestamps older than 1 second
            self.timestamps = [t for t in self.timestamps if now - t < 1.0]

            if len(self.timestamps) >= self.max_per_second:
                # Wait until the oldest timestamp is more than 1 second old
                sleep_time = 1.0 - (now - self.timestamps[0])
                if sleep_time > 0:
                    time.sleep(sleep_time)
                    # Clean up again after sleeping
                    now = time.monotonic()
                    self.timestamps = [t for t in self.timestamps if now - t < 1.0]

            self.timestamps.append(time.monotonic())
