from datetime import datetime
from decimal import Decimal
from enum import Enum

from pydantic import BaseModel


class Currency(str, Enum):
    xDai = "xDai"
    Mana = "Mana"


class Resolution(str, Enum):
    YES = "YES"
    NO = "NO"
    CANCEL = "CANCEL"
    MKT = "MKT"


class BetAmount(BaseModel):
    amount: Decimal
    currency: Currency


class ProfitAmount(BaseModel):
    amount: Decimal
    currency: Currency


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
