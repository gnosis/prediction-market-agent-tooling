from datetime import datetime
from enum import Enum
from typing import Annotated, TypeAlias

from pydantic import BaseModel, BeforeValidator, computed_field

from prediction_market_agent_tooling.gtypes import OutcomeStr, Probability


class Currency(str, Enum):
    xDai = "xDai"
    Mana = "Mana"
    USDC = "USDC"


class Resolution(str, Enum):
    YES = "YES"
    NO = "NO"
    CANCEL = "CANCEL"
    MKT = "MKT"

    @staticmethod
    def from_bool(value: bool) -> "Resolution":
        return Resolution.YES if value else Resolution.NO


class TokenAmount(BaseModel):
    amount: float
    currency: Currency

    def __str__(self) -> str:
        return f"Amount {self.amount} currency {self.currency}"


BetAmount: TypeAlias = TokenAmount
ProfitAmount: TypeAlias = TokenAmount


class Bet(BaseModel):
    amount: BetAmount
    outcome: bool
    created_time: datetime
    market_question: str
    market_id: str

    def __str__(self) -> str:
        return f"Bet for market {self.market_id} for question {self.market_question} created at {self.created_time}: {self.amount} on {self.outcome}"


class ResolvedBet(Bet):
    market_outcome: bool
    resolved_time: datetime
    profit: ProfitAmount

    @computed_field  # type: ignore[prop-decorator]
    @property
    def is_correct(self) -> bool:
        return self.outcome == self.market_outcome

    def __str__(self) -> str:
        return f"Resolved bet for market {self.market_id} for question {self.market_question} created at {self.created_time}: {self.amount} on {self.outcome}. Bet was resolved at {self.resolved_time} and was {'correct' if self.is_correct else 'incorrect'}. Profit was {self.profit}"


class TokenAmountAndDirection(TokenAmount):
    direction: bool


def to_boolean_outcome(value: str | bool) -> bool:
    if isinstance(value, bool):
        return value

    elif isinstance(value, str):
        value = value.lower().strip()

        if value in {"true", "yes", "y", "1"}:
            return True

        elif value in {"false", "no", "n", "0"}:
            return False

        else:
            raise ValueError(f"Expected a boolean string, but got {value}")

    else:
        raise ValueError(f"Expected a boolean or a string, but got {value}")


Decision = Annotated[bool, BeforeValidator(to_boolean_outcome)]


class ProbabilisticAnswer(BaseModel):
    p_yes: Probability
    confidence: float
    reasoning: str | None = None

    @property
    def p_no(self) -> Probability:
        return Probability(1 - self.p_yes)


class Position(BaseModel):
    market_id: str
    amounts: dict[OutcomeStr, TokenAmount]

    @property
    def total_amount(self) -> TokenAmount:
        return TokenAmount(
            amount=sum(amount.amount for amount in self.amounts.values()),
            currency=self.amounts[next(iter(self.amounts.keys()))].currency,
        )

    def __str__(self) -> str:
        amounts_str = ", ".join(
            f"{amount.amount} '{outcome}' tokens"
            for outcome, amount in self.amounts.items()
        )
        return f"Position for market id {self.market_id}: {amounts_str}"
