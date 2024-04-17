from datetime import datetime
from enum import Enum
from typing import TypeAlias

from pydantic import BaseModel


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
