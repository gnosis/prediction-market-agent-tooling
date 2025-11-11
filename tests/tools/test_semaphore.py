import asyncio
import time

import pytest

from prediction_market_agent_tooling.config import APIKeys
from prediction_market_agent_tooling.tools.cow.semaphore import postgres_rate_limited


def test_sync_function_rate_limit() -> None:
    """Test that the rate limiter works with synchronous functions."""
    call_times: list[float] = []

    @postgres_rate_limited(
        api_keys=APIKeys(),
        rate_id="test_sync_rate_limit",
        interval_seconds=0.5,
        shared_db=False,
    )
    def sync_function() -> str:
        call_times.append(time.time())
        return "sync_result"

    # Call the function multiple times
    result1 = sync_function()
    result2 = sync_function()
    result3 = sync_function()

    # Verify results
    assert result1 == "sync_result"
    assert result2 == "sync_result"
    assert result3 == "sync_result"

    # Verify rate limiting: should have at least 0.5 seconds between calls
    assert len(call_times) == 3
    assert call_times[1] - call_times[0] >= 0.5
    assert call_times[2] - call_times[1] >= 0.5


@pytest.mark.asyncio
async def test_async_function_rate_limit() -> None:
    """Test that the rate limiter works with asynchronous functions."""
    call_times: list[float] = []

    @postgres_rate_limited(
        api_keys=APIKeys(),
        rate_id="test_async_rate_limit",
        interval_seconds=0.5,
        shared_db=False,
    )
    async def async_function() -> str:
        call_times.append(time.time())
        await asyncio.sleep(0.01)  # Simulate async work
        return "async_result"

    # Call the function multiple times
    result1 = await async_function()
    result2 = await async_function()
    result3 = await async_function()

    # Verify results
    assert result1 == "async_result"
    assert result2 == "async_result"
    assert result3 == "async_result"

    # Verify rate limiting: should have at least 0.5 seconds between calls
    assert len(call_times) == 3
    assert call_times[1] - call_times[0] >= 0.5
    assert call_times[2] - call_times[1] >= 0.5


def test_sync_function_with_args() -> None:
    """Test that the rate limiter preserves function arguments."""

    @postgres_rate_limited(
        api_keys=APIKeys(),
        rate_id="test_sync_with_args",
        interval_seconds=0.1,
        shared_db=False,
    )
    def function_with_args(a: int, b: str, c: bool = True) -> tuple[int, str, bool]:
        return a, b, c

    result = function_with_args(42, "test", c=False)
    assert result == (42, "test", False)


@pytest.mark.asyncio
async def test_async_function_with_args() -> None:
    """Test that the rate limiter preserves function arguments for async functions."""

    @postgres_rate_limited(
        api_keys=APIKeys(),
        rate_id="test_async_with_args",
        interval_seconds=0.1,
        shared_db=False,
    )
    async def async_function_with_args(
        a: int, b: str, c: bool = True
    ) -> tuple[int, str, bool]:
        return a, b, c

    result = await async_function_with_args(42, "test", c=False)
    assert result == (42, "test", False)


def test_sync_different_rate_ids() -> None:
    """Test that different rate_ids maintain independent rate limits."""
    calls_a: list[float] = []
    calls_b: list[float] = []

    @postgres_rate_limited(
        api_keys=APIKeys(),
        rate_id="test_sync_rate_a",
        interval_seconds=0.3,
        shared_db=False,
    )
    def function_a() -> str:
        calls_a.append(time.time())
        return "a"

    @postgres_rate_limited(
        api_keys=APIKeys(),
        rate_id="test_sync_rate_b",
        interval_seconds=0.3,
        shared_db=False,
    )
    def function_b() -> str:
        calls_b.append(time.time())
        return "b"

    # Call both functions - they should not interfere with each other
    function_a()
    function_b()
    function_a()
    function_b()

    # Each function should be rate limited independently
    assert len(calls_a) == 2
    assert len(calls_b) == 2
    assert calls_a[1] - calls_a[0] >= 0.3
    assert calls_b[1] - calls_b[0] >= 0.3


@pytest.mark.asyncio
async def test_async_different_rate_ids() -> None:
    """Test that different rate_ids maintain independent rate limits for async functions."""
    calls_a: list[float] = []
    calls_b: list[float] = []

    @postgres_rate_limited(
        api_keys=APIKeys(),
        rate_id="test_async_rate_a",
        interval_seconds=0.3,
        shared_db=False,
    )
    async def async_function_a() -> str:
        calls_a.append(time.time())
        return "a"

    @postgres_rate_limited(
        api_keys=APIKeys(),
        rate_id="test_async_rate_b",
        interval_seconds=0.3,
        shared_db=False,
    )
    async def async_function_b() -> str:
        calls_b.append(time.time())
        return "b"

    # Call both functions - they should not interfere with each other
    await async_function_a()
    await async_function_b()
    await async_function_a()
    await async_function_b()

    # Each function should be rate limited independently
    assert len(calls_a) == 2
    assert len(calls_b) == 2
    assert calls_a[1] - calls_a[0] >= 0.3
    assert calls_b[1] - calls_b[0] >= 0.3
