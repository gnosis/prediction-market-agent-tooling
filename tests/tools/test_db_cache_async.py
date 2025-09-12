import asyncio
from datetime import timedelta

import pytest
from pydantic import BaseModel

from prediction_market_agent_tooling.config import APIKeys
from prediction_market_agent_tooling.tools.caches.db_cache import db_cache


@pytest.mark.asyncio
async def test_async_postgres_cache_integers(
    session_keys_with_postgresql_proc_and_enabled_cache: APIKeys,
) -> None:
    call_count = 0

    @db_cache(api_keys=session_keys_with_postgresql_proc_and_enabled_cache)
    async def integers(a: int, b: int) -> int:
        nonlocal call_count
        call_count += 1
        return a * b

    assert await integers(2, 3) == 6
    # Allow background cache save to complete
    await asyncio.sleep(0.1)
    assert await integers(2, 3) == 6
    assert await integers(4, 5) == 20
    assert call_count == 2, "The function should only be called twice due to caching"


@pytest.mark.asyncio
async def test_async_postgres_cache_none(
    session_keys_with_postgresql_proc_and_enabled_cache: APIKeys,
) -> None:
    call_count = 0

    @db_cache(api_keys=session_keys_with_postgresql_proc_and_enabled_cache)
    async def returns_none() -> None:
        nonlocal call_count
        call_count += 1
        return None

    assert await returns_none() is None  # type: ignore[func-returns-value]
    await asyncio.sleep(0.1)
    assert await returns_none() is None  # type: ignore[func-returns-value]
    await asyncio.sleep(0.1)
    assert await returns_none() is None  # type: ignore[func-returns-value]
    assert call_count == 1, "The function should only be called once due to caching"


@pytest.mark.asyncio
async def test_async_postgres_cache_do_not_cache_none(
    session_keys_with_postgresql_proc_and_enabled_cache: APIKeys,
) -> None:
    call_count = 0

    @db_cache(
        api_keys=session_keys_with_postgresql_proc_and_enabled_cache, cache_none=False
    )
    async def returns_none() -> None:
        nonlocal call_count
        call_count += 1
        return None

    assert await returns_none() is None  # type: ignore[func-returns-value]
    assert await returns_none() is None  # type: ignore[func-returns-value]
    assert await returns_none() is None  # type: ignore[func-returns-value]
    assert (
        call_count == 3
    ), "The function should be called 3 times because cache_none is False"


class TestInputModel(BaseModel):
    value: int


class TestOutputModel(BaseModel):
    result: int


@pytest.mark.asyncio
async def test_async_postgres_cache_pydantic_models(
    session_keys_with_postgresql_proc_and_enabled_cache: APIKeys,
) -> None:
    call_count = 0

    @db_cache(api_keys=session_keys_with_postgresql_proc_and_enabled_cache)
    async def multiply_models(a: TestInputModel, b: TestInputModel) -> TestOutputModel:
        nonlocal call_count
        call_count += 1
        return TestOutputModel(result=a.value * b.value)

    assert await multiply_models(
        TestInputModel(value=2), TestInputModel(value=3)
    ) == TestOutputModel(result=6)
    await asyncio.sleep(0.1)
    assert await multiply_models(
        TestInputModel(value=2), TestInputModel(value=3)
    ) == TestOutputModel(result=6)
    assert await multiply_models(
        TestInputModel(value=4), TestInputModel(value=5)
    ) == TestOutputModel(result=20)
    assert call_count == 2, "The function should only be called twice due to caching"
