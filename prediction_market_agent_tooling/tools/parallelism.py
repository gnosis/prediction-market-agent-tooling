from typing import Callable, Generator, TypeVar

from loky import get_reusable_executor

A = TypeVar("A")
B = TypeVar("B")


def par_map(
    items: list[A],
    func: Callable[[A], B],
    max_workers: int = 5,
) -> "list[B]":
    """Applies the function to each element using the specified executor. Awaits for all results."""
    executor = get_reusable_executor(max_workers=max_workers)
    futures = [executor.submit(func, item) for item in items]
    results = []
    for fut in futures:
        results.append(fut.result())
    return results


def par_generator(
    items: list[A],
    func: Callable[[A], B],
    max_workers: int = 5,
) -> Generator[B, None, None]:
    """Applies the function to each element using the specified executor. Yields results as they come."""
    executor = get_reusable_executor(max_workers=max_workers)
    for fut in executor.map(func, items):
        yield fut
