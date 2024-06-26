from datetime import datetime
from enum import Enum
from typing import TypeAlias

from pydantic import BaseModel

from prediction_market_agent_tooling.gtypes import OutcomeStr


class Currency(str, Enum):
    xDai = "xDai"
    Mana = "Mana"
    USDC = "USDC"


class Resolution(str, Enum):
    YES = "YES"
    NO = "NO"
    CANCEL = "CANCEL"
    MKT = "MKT"


class TokenAmount(BaseModel):
    amount: float
    currency: Currency


BetAmount: TypeAlias = TokenAmount
ProfitAmount: TypeAlias = TokenAmount


class Bet(BaseModel):
    amount: BetAmount
    outcome: bool
    created_time: datetime
    market_question: str


class ResolvedBet(Bet):
    market_outcome: bool
    resolved_time: datetime
    profit: ProfitAmount

    @property
    def is_correct(self) -> bool:
        return self.outcome == self.market_outcome


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
