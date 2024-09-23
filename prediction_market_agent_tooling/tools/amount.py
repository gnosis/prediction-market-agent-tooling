from abc import ABC, abstractmethod
from typing import Callable


class Amount(ABC):
    @abstractmethod
    def get(self) -> float:
        """
        Returns the amount
        """


class StaticAmount(Amount):
    def __init__(self, amount: float):
        self.amount = amount

    def get(self) -> float:
        return self.amount


class DynamicAmount(Amount):
    def __init__(self, get_amount_fn: Callable[[], float], proportion: float = 1.0):
        self.get_wallet_balance_fn = get_amount_fn
        self.proportion = proportion

    def get(self) -> float:
        return self.get_wallet_balance_fn() * self.proportion
