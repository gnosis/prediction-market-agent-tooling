from datetime import date, timedelta

from pydantic import BaseModel

from prediction_market_agent_tooling.config import APIKeys
from prediction_market_agent_tooling.tools.caches.db_cache import db_cache
from prediction_market_agent_tooling.tools.datetime_utc import DatetimeUTC
from prediction_market_agent_tooling.tools.parallelism import par_map


def test_postgres_cache_bools(
    keys_with_sqlalchemy_db_url: APIKeys,
) -> None:
    call_count = 0

    @db_cache(api_keys=keys_with_sqlalchemy_db_url)
    def bools(
        a: bool,
    ) -> bool:
        nonlocal call_count
        call_count += 1
        return a

    assert bools(True) == True
    assert bools(True) == True
    assert bools(False) == False
    assert call_count == 2, "The function should only be called twice due to caching"


def test_postgres_cache_integers(
    keys_with_sqlalchemy_db_url: APIKeys,
) -> None:
    call_count = 0

    @db_cache(api_keys=keys_with_sqlalchemy_db_url)
    def integers(a: int, b: int) -> int:
        nonlocal call_count
        call_count += 1
        return a * b

    assert integers(2, 3) == 6
    assert integers(2, 3) == 6
    assert integers(4, 5) == 20
    assert call_count == 2, "The function should only be called twice due to caching"


def test_postgres_cache_none(
    keys_with_sqlalchemy_db_url: APIKeys,
) -> None:
    call_count = 0

    @db_cache(api_keys=keys_with_sqlalchemy_db_url)
    def integers() -> None:
        nonlocal call_count
        call_count += 1
        return None

    assert integers() is None
    assert integers() is None
    assert integers() is None
    assert call_count == 1, "The function should only be called once due to caching"


def test_postgres_cache_do_not_cache_none(
    keys_with_sqlalchemy_db_url: APIKeys,
) -> None:
    call_count = 0

    @db_cache(api_keys=keys_with_sqlalchemy_db_url, cache_none=False)
    def integers() -> None:
        nonlocal call_count
        call_count += 1
        return None

    assert integers() is None
    assert integers() is None
    assert integers() is None
    assert (
        call_count == 3
    ), "The function should be called 3 times because cache_none is False"


def test_postgres_cache_disabled_cache(
    keys_with_sqlalchemy_db_url: APIKeys,
) -> None:
    keys_with_sqlalchemy_db_url = keys_with_sqlalchemy_db_url.model_copy(
        update={"ENABLE_CACHE": False}
    )
    call_count = 0

    @db_cache(api_keys=keys_with_sqlalchemy_db_url)
    def integers() -> int:
        nonlocal call_count
        call_count += 1
        return call_count

    assert integers() == 1
    assert integers() == 2
    assert integers() == 3
    assert (
        call_count == 3
    ), "The function should be called 3 times because ENABLE_CACHE is disabled"


def test_postgres_cache_strings(
    keys_with_sqlalchemy_db_url: APIKeys,
) -> None:
    call_count = 0

    @db_cache(api_keys=keys_with_sqlalchemy_db_url)
    def concatenate(a: str, b: str) -> str:
        nonlocal call_count
        call_count += 1
        return a + b

    assert concatenate("hello", "dog") == "hellodog"
    assert concatenate("hello", "dog") == "hellodog"
    assert concatenate("foo", "bar") == "foobar"
    assert call_count == 2, "The function should only be called twice due to caching"


def test_postgres_cache_datetimes(
    keys_with_sqlalchemy_db_url: APIKeys,
) -> None:
    call_count = 0

    @db_cache(api_keys=keys_with_sqlalchemy_db_url)
    def add_timedelta(dt: DatetimeUTC, delta: timedelta) -> DatetimeUTC:
        nonlocal call_count
        call_count += 1
        return dt + delta

    dt = DatetimeUTC(2023, 1, 1)
    assert add_timedelta(dt, timedelta(days=5)) == DatetimeUTC(2023, 1, 6)
    assert add_timedelta(dt, timedelta(days=5)) == DatetimeUTC(2023, 1, 6)
    assert add_timedelta(dt, timedelta(days=10)) == DatetimeUTC(2023, 1, 11)
    assert call_count == 2, "The function should only be called twice due to caching"


def test_postgres_cache_datess(
    keys_with_sqlalchemy_db_url: APIKeys,
) -> None:
    call_count = 0

    @db_cache(api_keys=keys_with_sqlalchemy_db_url)
    def add_timedelta(dt: date, delta: timedelta) -> date:
        nonlocal call_count
        call_count += 1
        return dt + delta

    dt = date(2023, 1, 1)
    assert add_timedelta(dt, timedelta(days=5)) == date(2023, 1, 6)
    assert add_timedelta(dt, timedelta(days=5)) == date(2023, 1, 6)
    assert add_timedelta(dt, timedelta(days=10)) == date(2023, 1, 11)
    assert call_count == 2, "The function should only be called twice due to caching"


def test_postgres_cache_lists(
    keys_with_sqlalchemy_db_url: APIKeys,
) -> None:
    call_count = 0

    @db_cache(api_keys=keys_with_sqlalchemy_db_url)
    def merge_lists(a: list[int], b: list[int]) -> list[int]:
        nonlocal call_count
        call_count += 1
        return a + b

    assert merge_lists([1, 2], [3, 4]) == [1, 2, 3, 4]
    assert merge_lists([1, 2], [3, 4]) == [1, 2, 3, 4]
    assert merge_lists([5], [6, 7]) == [5, 6, 7]
    assert call_count == 2, "The function should only be called twice due to caching"


class TestInputModel(BaseModel):
    value: int


class TestOutputModel(BaseModel):
    result: int


def test_postgres_cache_pydantic_models(
    keys_with_sqlalchemy_db_url: APIKeys,
) -> None:
    call_count = 0

    @db_cache(api_keys=keys_with_sqlalchemy_db_url)
    def multiply_models(a: TestInputModel, b: TestInputModel) -> TestOutputModel:
        nonlocal call_count
        call_count += 1
        return TestOutputModel(result=a.value * b.value)

    assert multiply_models(
        TestInputModel(value=2), TestInputModel(value=3)
    ) == TestOutputModel(result=6)
    assert multiply_models(
        TestInputModel(value=2), TestInputModel(value=3)
    ) == TestOutputModel(result=6)
    assert multiply_models(
        TestInputModel(value=4), TestInputModel(value=5)
    ) == TestOutputModel(result=20)
    assert call_count == 2, "The function should only be called twice due to caching"


def test_postgres_cache_pydantic_models_list(
    keys_with_sqlalchemy_db_url: APIKeys,
) -> None:
    call_count = 0

    @db_cache(api_keys=keys_with_sqlalchemy_db_url)
    def multiply_models(a: TestInputModel, b: TestInputModel) -> list[TestOutputModel]:
        nonlocal call_count
        call_count += 1
        return [TestOutputModel(result=a.value * b.value)]

    assert multiply_models(TestInputModel(value=2), TestInputModel(value=3)) == [
        TestOutputModel(result=6)
    ]
    assert multiply_models(TestInputModel(value=2), TestInputModel(value=3)) == [
        TestOutputModel(result=6)
    ]
    assert multiply_models(TestInputModel(value=4), TestInputModel(value=5)) == [
        TestOutputModel(result=20)
    ]
    assert call_count == 2, "The function should only be called twice due to caching"


def test_postgres_cache_pydantic_models_dict_list(
    keys_with_sqlalchemy_db_url: APIKeys,
) -> None:
    call_count = 0

    @db_cache(api_keys=keys_with_sqlalchemy_db_url)
    def multiply_models(
        a: TestInputModel, b: TestInputModel
    ) -> list[dict[str, TestOutputModel]]:
        nonlocal call_count
        call_count += 1
        return [{"a": TestOutputModel(result=a.value * b.value)}]

    assert multiply_models(TestInputModel(value=2), TestInputModel(value=3)) == [
        {"a": TestOutputModel(result=6)}
    ]
    assert multiply_models(TestInputModel(value=2), TestInputModel(value=3)) == [
        {"a": TestOutputModel(result=6)}
    ]
    assert multiply_models(TestInputModel(value=4), TestInputModel(value=5)) == [
        {"a": TestOutputModel(result=20)}
    ]
    assert call_count == 2, "The function should only be called twice due to caching"


def test_postgres_cache_pydantic_models_will_be_invalidated_after_change(
    keys_with_sqlalchemy_db_url: APIKeys,
) -> None:
    call_count = 0

    # Initial output model
    class FirstOutputModel(TestOutputModel):
        pass

    @db_cache(api_keys=keys_with_sqlalchemy_db_url)
    def multiply_models(a: TestInputModel, b: TestInputModel) -> FirstOutputModel:
        nonlocal call_count
        call_count += 1
        return FirstOutputModel(result=a.value * b.value)

    assert multiply_models(
        TestInputModel(value=2), TestInputModel(value=3)
    ) == FirstOutputModel(result=6)

    # Define a new output model to invalidate the cache
    class FirstOutputModel(TestOutputModel):  # type: ignore[no-redef] # Mypy complains, because `FirstOutputModel` was defined two times, but that's the point of this test.
        # If you would remove this field here, and just do `pass`, this test would fail, because cache wasn't invalidated (the model has same name and requried arguments).
        # In reality, we won't define two classes with the same name in a single file, but what could happen is adding a new required field to the model, making it incompatible with the previously stored cached data.
        new_field: str

    # Redefine the function to return the new output model
    @db_cache(api_keys=keys_with_sqlalchemy_db_url)  # type: ignore[no-redef] # Need to redefine the function as well, otherwise it would remember the original model.
    def multiply_models(a: TestInputModel, b: TestInputModel) -> FirstOutputModel:
        nonlocal call_count
        call_count += 1
        return FirstOutputModel(result=a.value * b.value, new_field="modified")  # type: ignore # Mypy complains, because `FirstOutputModel` was defined two times, but that's the point of this test.

    assert multiply_models(
        TestInputModel(value=2), TestInputModel(value=3)
    ) == FirstOutputModel(
        result=6, new_field="modified"
    )  # type: ignore # Mypy complains, because `FirstOutputModel` was defined two times, but that's the point of this test.
    assert multiply_models(
        TestInputModel(value=4), TestInputModel(value=5)
    ) == FirstOutputModel(
        result=20, new_field="modified"
    )  # type: ignore # Mypy complains, because `FirstOutputModel` was defined two times, but that's the point of this test.
    assert (
        call_count == 3
    ), "The function should be called three times due to cache invalidation"


def test_postgres_cache_ignored_arg_names_and_types(
    keys_with_sqlalchemy_db_url: APIKeys,
) -> None:
    call_count = 0

    @db_cache(
        api_keys=keys_with_sqlalchemy_db_url,
        ignore_args=["a"],
        ignore_arg_types=[str],
    )
    def integers(a: int, b: str, c: float) -> None:
        nonlocal call_count
        call_count += 1
        return None

    assert integers(1, "1", 1.0) is None
    assert integers(2, "2", 1.0) is None
    assert integers(2, "2", 2.0) is None
    assert (
        call_count == 2
    ), "The function should only be called twice due to caching with ignored keys/types"


def test_db_cache_with_parallelism(keys_with_sqlalchemy_db_url: APIKeys) -> None:
    @db_cache(api_keys=keys_with_sqlalchemy_db_url)
    def twice(x: int) -> int:
        return x * 2

    results = par_map([1, 2, 3, 1, 2, 3], twice)
    assert results == [2, 4, 6, 2, 4, 6]
