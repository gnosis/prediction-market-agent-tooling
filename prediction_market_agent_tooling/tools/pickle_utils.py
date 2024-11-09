import typing as t

InitialisedValue = t.TypeVar("InitialisedValue")


class InitialiseNonPickable(t.Generic[InitialisedValue]):
    """
    Use this class to wrap values that you want to be shared within a thread,
    but they are re-initialised for a new processes.

    Initialiser for the value still needs to be pickable.
    """

    def __init__(self, initialiser: t.Callable[[], InitialisedValue]) -> None:
        self.value: InitialisedValue | None = None
        self.initialiser = initialiser

    def __getstate__(self) -> dict[str, t.Any]:
        # During pickling, always return `value` as just None, which is pickable and this class will re-initialise it in `get_value` when called.
        return {"value": None, "initialiser": self.initialiser}

    def __setstate__(self, d: dict[str, t.Any]) -> None:
        self.value = d["value"]
        self.initialiser = d["initialiser"]

    def get_value(self) -> InitialisedValue:
        """Use this function to get the wrapped value, which will be initialised if necessary."""
        if self.value is None:
            self.value = self.initialiser()

        return self.value
