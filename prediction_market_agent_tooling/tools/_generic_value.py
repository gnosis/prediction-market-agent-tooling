import typing as t
from decimal import Decimal
from typing import TypeVar, overload

from pydantic import GetCoreSchemaHandler
from pydantic_core import CoreSchema, core_schema
from web3.types import Wei as WeiWeb3

InputValueType = TypeVar(
    "InputValueType", bound=t.Union[str, int, float, WeiWeb3, Decimal]
)
InternalValueType = TypeVar("InternalValueType", bound=t.Union[int, float, WeiWeb3])


class _GenericValue(
    t.Generic[InputValueType, InternalValueType],
    # Not great, but it allows to serialize this object with plain json.
    dict[t.Literal["value"] | t.Literal["type"], InternalValueType | str],
):
    """
    A helper class intended for inheritance. Do not instantiate this class directly.

    Example:

    ```python
    a = _GenericValue(10)
    b = Token(100) # Token is a subclass of _GenericValue
    c = xDai(100) # xDai is a subclass of _GenericValue
    d = Mana(100) # Mana is a subclass of _GenericValue
    e = xDai(50)

    # Mypy will complain if we try to work with different currencies (types)
    b - c # mypy will report incompatible types
    c - d # mypy will report incompatible types
    c - e # mypy will be ok
    a - b # mypy won't report issues, as others are subclasses of _GenericValue, and that's a problem, so don't use _GenericValue directly

    # Resulting types after arithmetic operations are as expected, so we don't need to wrap them as before (e.g. xdai_type(c + c))
    x = c - e # x is of type xDai
    x = c * e # x if of type xDai
    x = c / e # x is of type float (pure value after division with same types)
    x = c / 2 # x is of type xDai
    x = c // 2 # x is of type xDai
    x * x * 2 # x is of type xDai
    ```

    TODO: There are some type ignores which isn't cool, but it works and type-wise values are also correct. Idk how to explain it to mypy though.
    """

    GenericValueType = TypeVar(
        "GenericValueType", bound="_GenericValue[InputValueType, InternalValueType]"
    )

    parser: t.Callable[[InputValueType], InternalValueType]

    def __init_subclass__(
        cls, parser: t.Callable[[InputValueType], InternalValueType]
    ) -> None:
        super().__init_subclass__()
        cls.parser = parser

    def __init__(self, value: InputValueType) -> None:
        self.value: InternalValueType = self.parser(value)
        super().__init__({"value": self.value, "type": self.__class__.__name__})

    def __str__(self) -> str:
        return f"{self.value}"

    def __neg__(self: GenericValueType) -> GenericValueType:
        return type(self)(-self.value)  # type: ignore[arg-type]

    def __abs__(self: GenericValueType) -> GenericValueType:
        return type(self)(abs(self.value))  # type: ignore[arg-type]

    def __sub__(
        self: GenericValueType, other: GenericValueType | t.Literal[0]
    ) -> GenericValueType:
        if other == 0:
            other = self.zero()
        if not isinstance(other, _GenericValue):
            raise TypeError("Cannot subtract different types")
        if type(self) is not type(other):
            raise TypeError("Cannot subtract different types")
        return type(self)(self.value - other.value)

    def __add__(
        self: GenericValueType, other: GenericValueType | t.Literal[0]
    ) -> GenericValueType:
        if other == 0:
            other = self.zero()
        if not isinstance(other, _GenericValue):
            raise TypeError("Cannot add different types")
        if type(self) is not type(other):
            raise TypeError("Cannot add different types")
        return type(self)(self.value + other.value)

    def __mul__(
        self: GenericValueType, other: GenericValueType | int | float
    ) -> GenericValueType:
        if not isinstance(other, (_GenericValue, int, float)):
            raise TypeError("Cannot multiply different types")
        if not isinstance(other, (int, float)) and type(self) is not type(other):
            raise TypeError("Cannot multiply different types")
        return type(self)(self.value * (other if isinstance(other, (int, float)) else other.value))  # type: ignore

    @overload
    def __truediv__(self: GenericValueType, other: int | float) -> GenericValueType: ...

    @overload
    def __truediv__(
        self: GenericValueType, other: GenericValueType
    ) -> InternalValueType: ...

    def __truediv__(
        self: GenericValueType, other: GenericValueType | int | float
    ) -> GenericValueType | InternalValueType:
        if not isinstance(other, (_GenericValue, int, float)):
            raise TypeError("Cannot multiply different types")
        if not isinstance(other, (int, float)) and type(self) is not type(other):
            raise TypeError("Cannot multiply different types")
        if other == 0:
            raise ZeroDivisionError("Cannot divide by zero")
        if isinstance(other, (int, float)):
            return type(self)(self.value / other)  # type: ignore
        else:
            return self.value / other.value  # type: ignore

    @overload
    def __floordiv__(
        self: GenericValueType, other: int | float
    ) -> GenericValueType: ...

    @overload
    def __floordiv__(
        self: GenericValueType, other: GenericValueType
    ) -> InternalValueType: ...

    def __floordiv__(
        self: GenericValueType, other: GenericValueType | int | float
    ) -> GenericValueType | InternalValueType:
        if not isinstance(other, (_GenericValue, int, float)):
            raise TypeError("Cannot multiply different types")
        if not isinstance(other, (int, float)) and type(self) is not type(other):
            raise TypeError("Cannot multiply different types")
        if other == 0:
            raise ZeroDivisionError("Cannot divide by zero")
        if isinstance(other, (int, float)):
            return type(self)(self.value // other)  # type: ignore
        else:
            return self.value // other.value  # type: ignore

    def __lt__(self: GenericValueType, other: GenericValueType | t.Literal[0]) -> bool:
        if other == 0:
            other = self.zero()
        if not isinstance(other, _GenericValue):
            raise TypeError("Cannot compare different types")
        if type(self) is not type(other):
            raise TypeError("Cannot compare different types")
        return bool(self.value < other.value)

    def __le__(self: GenericValueType, other: GenericValueType | t.Literal[0]) -> bool:
        if other == 0:
            other = self.zero()
        if not isinstance(other, _GenericValue):
            raise TypeError("Cannot compare different types")
        if type(self) is not type(other):
            raise TypeError("Cannot compare different types")
        return bool(self.value <= other.value)

    def __gt__(self: GenericValueType, other: GenericValueType | t.Literal[0]) -> bool:
        if other == 0:
            other = self.zero()
        if not isinstance(other, _GenericValue):
            raise TypeError("Cannot compare different types")
        if type(self) is not type(other):
            raise TypeError("Cannot compare different types")
        return bool(self.value > other.value)

    def __ge__(self: GenericValueType, other: GenericValueType | t.Literal[0]) -> bool:
        if other == 0:
            other = self.zero()
        if not isinstance(other, _GenericValue):
            raise TypeError("Cannot compare different types")
        if type(self) is not type(other):
            raise TypeError("Cannot compare different types")
        return bool(self.value >= other.value)

    def __eq__(self: GenericValueType, other: GenericValueType | t.Literal[0]) -> bool:  # type: ignore
        if other == 0:
            other = self.zero()
        if not isinstance(other, _GenericValue):
            raise TypeError("Cannot compare different types")
        if type(self) is not type(other):
            raise TypeError("Cannot compare different types")
        return bool(self.value == other.value)

    def __ne__(self: GenericValueType, other: GenericValueType | t.Literal[0]) -> bool:  # type: ignore
        if other == 0:
            other = self.zero()
        if not isinstance(other, _GenericValue):
            raise TypeError("Cannot compare different types")
        if type(self) is not type(other):
            raise TypeError("Cannot compare different types")
        return bool(self.value != other.value)

    def __repr__(self) -> str:
        return f"{type(self).__name__}({self.value})"

    def __float__(self) -> float:
        return float(self.value)

    def __radd__(
        self: GenericValueType, other: GenericValueType | t.Literal[0] | int | float
    ) -> GenericValueType:
        if isinstance(other, (_GenericValue, int, float)):
            return self.__add__(other)  # type: ignore[operator]

        elif isinstance(other, (int, float)) and other == 0:
            return self

        else:
            raise TypeError("Cannot add different types")

    def __round__(self: GenericValueType, ndigits: int = 0) -> GenericValueType:
        if not isinstance(self.value, (int, float)):
            raise TypeError("Cannot round non-numeric types")
        return type(self)(round(self.value, ndigits))  # type: ignore[arg-type]

    def __bool__(self) -> bool:
        return bool(self.value)

    @classmethod
    def __get_pydantic_core_schema__(
        cls, source_type: t.Any, handler: GetCoreSchemaHandler
    ) -> CoreSchema:
        # Support for Pydantic usage.
        dt_schema = handler(str | int | float | dict)
        return core_schema.no_info_after_validator_function(
            lambda x: cls(x["value"] if isinstance(x, dict) else x),
            dt_schema,
        )

    def with_fraction(self: GenericValueType, fraction: float) -> GenericValueType:
        if not 0 <= fraction <= 1:
            raise ValueError(f"Given fraction {fraction} is not in the range [0,1].")
        return self.__class__(self.value * (1 + fraction))  # type: ignore[arg-type]

    def without_fraction(self: GenericValueType, fraction: float) -> GenericValueType:
        if not 0 <= fraction <= 1:
            raise ValueError(f"Given fraction {fraction} is not in the range [0,1].")
        return self.__class__(self.value * (1 - fraction))  # type: ignore[arg-type]

    @classmethod
    def zero(cls: type[GenericValueType]) -> GenericValueType:
        return cls(0)  # type: ignore[arg-type]
