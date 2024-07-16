import concurrent
from concurrent.futures import Executor
from concurrent.futures.process import ProcessPoolExecutor
from concurrent.futures.thread import ThreadPoolExecutor
from typing import Callable, Generator, TypeVar

# Max workers to 5 to avoid rate limiting on some APIs, create a custom executor if you need more workers.
DEFAULT_THREADPOOL_EXECUTOR = ThreadPoolExecutor(max_workers=5)
DEFAULT_PROCESSPOOL_EXECUTOR = ProcessPoolExecutor(max_workers=5)

A = TypeVar("A")
B = TypeVar("B")


def par_map(
    items: list[A],
    func: Callable[[A], B],
    executor: Executor = DEFAULT_THREADPOOL_EXECUTOR,
) -> "list[B]":
    """Applies the function to each element using the specified executor. Awaits for all results.
    If executor is ProcessPoolExecutor, make sure the function passed is pickable, e.g. no lambda functions
    """
    futures: list[concurrent.futures._base.Future[B]] = [
        executor.submit(func, item) for item in items
    ]
    results = []
    for fut in futures:
        results.append(fut.result())
    return results


def par_generator(
    items: list[A],
    func: Callable[[A], B],
    executor: Executor = DEFAULT_THREADPOOL_EXECUTOR,
) -> Generator[B, None, None]:
    """Applies the function to each element using the specified executor. Yields results as they come.
    If executor is ProcessPoolExecutor, make sure the function passed is pickable, e.g. no lambda functions.
    """
    futures: list[concurrent.futures._base.Future[B]] = [
        executor.submit(func, item) for item in items
    ]
    for fut in concurrent.futures.as_completed(futures):
        yield fut.result()
