import typing as t

_T = t.TypeVar("_T")


class SingletonMeta(type, t.Generic[_T]):
    """
    The Singleton class can be implemented in different ways in Python. Some
    possible methods include: base class, decorator, metaclass. We will use the
    metaclass because it is best suited for this purpose.

    This version creates a unique instance for each unique set of __init__ arguments.
    """

    _instances: dict[
        tuple[t.Any, tuple[t.Any, ...], tuple[tuple[str, t.Any], ...]], _T
    ] = {}

    def __call__(self, *args: t.Any, **kwargs: t.Any) -> _T:
        """
        Different __init__ arguments will result in different instances.
        """
        # Create a key based on the class, args, and kwargs (sorted for consistency)
        key = (self, args, tuple(sorted(kwargs.items())))
        if key not in self._instances:
            instance = super().__call__(*args, **kwargs)
            self._instances[key] = instance
        return self._instances[key]
