from datetime import datetime
from enum import Enum
from typing import TypeAlias

from eth_typing import HexAddress
from pydantic import BaseModel, computed_field

from prediction_market_agent_tooling.gtypes import OutcomeStr


class Currency(str, Enum):
    xDai = "xDai"
    Mana = "Mana"
    USDC = "USDC"

    def __str__(self) -> str:
        return self.value


class Resolution(str, Enum):
    YES = "YES"
    NO = "NO"
    CANCEL = "CANCEL"
    MKT = "MKT"


class TokenAmount(BaseModel):
    amount: float
    currency: Currency

    def __str__(self) -> str:
        return "Amount {} currency {}".format(self.amount, self.currency)


BetAmount: TypeAlias = TokenAmount
ProfitAmount: TypeAlias = TokenAmount


class Bet(BaseModel):
    amount: BetAmount
    outcome: bool
    created_time: datetime
    market_question: str
    market_id: HexAddress

    def __str__(self) -> str:
        return f"Bet for market {self.market_id} for question {self.market_question} created at {self.created_time}: {self.amount} on {self.outcome}"


class ResolvedBet(Bet):
    market_outcome: bool
    resolved_time: datetime
    profit: ProfitAmount

    @computed_field  # type: ignore[misc]
    @property
    def is_correct(self) -> bool:
        return self.outcome == self.market_outcome

    def __str__(self) -> str:
        return f"Resolved bet for market {self.market_id} for question {self.market_question} created at {self.created_time}: {self.amount} on {self.outcome}. Bet was resolved at {self.resolved_time} and was {'correct' if self.is_correct else 'incorrect'}. Profit was {self.profit}"


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
