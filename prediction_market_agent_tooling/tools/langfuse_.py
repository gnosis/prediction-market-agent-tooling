from typing import Any, Callable, Iterable, Literal, Optional, ParamSpec, TypeVar

from langfuse.decorators.langfuse_decorator import (  # noqa: F401  # Import for the sake of easy importing with others from here.
    langfuse_context,
)
from langfuse.decorators.langfuse_decorator import observe as original_observe

P = ParamSpec("P")
R = TypeVar("R")


def observe(
    name: Optional[str] = None,
    as_type: Optional[Literal["generation"]] = None,
    capture_input: bool = True,
    capture_output: bool = True,
    transform_to_string: Optional[Callable[[Iterable[Any]], str]] = None,
) -> Callable[[Callable[P, R]], Callable[P, R]]:
    casted: Callable[[Callable[P, R]], Callable[P, R]] = original_observe(
        name=name,
        as_type=as_type,
        capture_input=capture_input,
        capture_output=capture_output,
        transform_to_string=transform_to_string,
    )
    return casted
