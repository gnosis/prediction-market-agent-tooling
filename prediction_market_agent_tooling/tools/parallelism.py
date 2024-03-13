import concurrent
import os
from concurrent.futures import Executor
from concurrent.futures.thread import ThreadPoolExecutor
from typing import Callable, TypeVar

max_workers = os.getenv("THREADPOOL_N_THREADS") or None
THREADPOOL = ThreadPoolExecutor(max_workers=max_workers)

A = TypeVar("A")
B = TypeVar("B")


def par_map(
    items: list[A], func: Callable[[A], B], executor: Executor = THREADPOOL
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
