import typing as t
from decimal import Decimal

from pydantic import BaseModel

from prediction_market_agent_tooling.gtypes import Probability
from prediction_market_agent_tooling.markets.data_models import BetAmount, Currency


class AgentMarket(BaseModel):
    """
    Common market class that can be created from vendor specific markets.
    Contains everything that is needed for an agent to make a prediction.
    """

    currency: t.ClassVar[Currency]

    id: str
    question: str
    outcomes: list[str]
    p_yes: Probability

    @property
    def p_no(self) -> float:
        return 1 - self.p_yes

    def get_bet_amount(self, amount: Decimal) -> BetAmount:
        return BetAmount(amount=amount, currency=self.currency)

    def get_tiny_bet_amount(self) -> BetAmount:
        raise NotImplementedError("Subclasses must implement this method")

    def place_bet(self, outcome: bool, amount: BetAmount) -> None:
        raise NotImplementedError("Subclasses must implement this method")

    @staticmethod
    def get_binary_markets(limit: int) -> list["AgentMarket"]:
        raise NotImplementedError("Subclasses must implement this method")

    def get_outcome_str(self, outcome_index: int) -> str:
        try:
            return self.outcomes[outcome_index]
        except IndexError:
            raise IndexError(
                f"Outcome index `{outcome_index}` out of range for `{self.outcomes}`: `{self.outcomes}`."
            )

    def get_outcome_index(self, outcome: str) -> int:
        try:
            return self.outcomes.index(outcome)
        except ValueError:
            raise ValueError(f"Outcome `{outcome}` not found in `{self.outcomes}`.")
