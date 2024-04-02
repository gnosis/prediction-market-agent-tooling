import typing as t

_T = t.TypeVar("_T")


class SingletonMeta(type, t.Generic[_T]):
    """
    The Singleton class can be implemented in different ways in Python. Some
    possible methods include: base class, decorator, metaclass. We will use the
    metaclass because it is best suited for this purpose.
    """

    _instances: dict[t.Any, _T] = {}

    def __call__(cls, *args: t.Any, **kwargs: t.Any) -> _T:
        """
        Possible changes to the value of the `__init__` argument do not affect
        the returned instance.
        """
        if cls not in cls._instances:
            instance = super().__call__(*args, **kwargs)
            cls._instances[cls] = instance
        return cls._instances[cls]
