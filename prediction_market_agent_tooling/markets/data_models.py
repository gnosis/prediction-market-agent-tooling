from enum import Enum
from typing import Annotated

from pydantic import BaseModel, BeforeValidator, computed_field

from prediction_market_agent_tooling.gtypes import (
    USD,
    CollateralToken,
    OutcomeStr,
    OutcomeToken,
    Probability,
)
from prediction_market_agent_tooling.tools.utils import DatetimeUTC


class Resolution(str, Enum):
    YES = "YES"
    NO = "NO"
    CANCEL = "CANCEL"
    MKT = "MKT"

    @staticmethod
    def from_bool(value: bool) -> "Resolution":
        return Resolution.YES if value else Resolution.NO


class Bet(BaseModel):
    id: str
    amount: CollateralToken
    outcome: bool
    created_time: DatetimeUTC
    market_question: str
    market_id: str

    def __str__(self) -> str:
        return f"Bet for market {self.market_id} for question {self.market_question} created at {self.created_time}: {self.amount} on {self.outcome}"


class ResolvedBet(Bet):
    market_outcome: bool
    resolved_time: DatetimeUTC
    profit: CollateralToken

    @computed_field  # type: ignore[prop-decorator]
    @property
    def is_correct(self) -> bool:
        return self.outcome == self.market_outcome

    def __str__(self) -> str:
        return f"Resolved bet for market {self.market_id} for question {self.market_question} created at {self.created_time}: {self.amount} on {self.outcome}. Bet was resolved at {self.resolved_time} and was {'correct' if self.is_correct else 'incorrect'}. Profit was {self.profit}"


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


class MultiOutcomeProbabilisticAnswer(BaseModel):
    # ToDo - Validate probabilities using Pydantic model validation
    probabilities: dict[OutcomeStr, Probability]
    confidence: float
    reasoning: str | None = None


class ProbabilisticAnswer(BaseModel):
    # p_yes: Probability
    probabilities_multi: dict[OutcomeStr, Probability]
    confidence: float
    reasoning: str | None = None

    def get_yes_probability(self) -> Probability | None:
        return next(
            (p for o, p in self.probabilities_multi.items() if o.upper() == OMEN_TRUE_OUTCOME.upper()), None
        )


class Position(BaseModel):
    market_id: str
    # This is for how much we could buy or sell the position right now.
    amounts_current: dict[OutcomeStr, USD]

    @property
    def total_amount_current(self) -> USD:
        return sum(self.amounts_current.values(), start=USD(0))

    def __str__(self) -> str:
        amounts_str = ", ".join(
            f"{amount} USD of '{outcome}' tokens"
            for outcome, amount in self.amounts_current.items()
        )
        return f"Position for market id {self.market_id}: {amounts_str}"


class ExistingPosition(Position):
    # This is how much we will get if we win.
    amounts_potential: dict[OutcomeStr, USD]
    # These are raw outcome tokens of the market.
    amounts_ot: dict[OutcomeStr, OutcomeToken]

    @property
    def total_amount_potential(self) -> USD:
        return sum(self.amounts_potential.values(), start=USD(0))

    @property
    def total_amount_ot(self) -> OutcomeToken:
        return sum(self.amounts_ot.values(), start=OutcomeToken(0))


class TradeType(str, Enum):
    SELL = "sell"
    BUY = "buy"


class Trade(BaseModel):
    trade_type: TradeType
    # outcome: bool
    outcome: OutcomeStr
    amount: USD


class PlacedTrade(Trade):
    id: str | None = None

    @staticmethod
    def from_trade(trade: Trade, id: str) -> "PlacedTrade":
        return PlacedTrade(
            trade_type=trade.trade_type,
            outcome=trade.outcome,
            amount=trade.amount,
            id=id,
        )


class SimulatedBetDetail(BaseModel):
    strategy: str
    url: str
    market_p_yes: float
    agent_p_yes: float
    agent_conf: float
    org_bet: CollateralToken
    sim_bet: CollateralToken
    org_dir: bool
    sim_dir: bool
    org_profit: CollateralToken
    sim_profit: CollateralToken
    timestamp: DatetimeUTC


class SharpeOutput(BaseModel):
    annualized_volatility: float
    mean_daily_return: float
    annualized_sharpe_ratio: float


class SimulatedLifetimeDetail(BaseModel):
    p_yes_mse: float
    total_bet_amount: CollateralToken
    total_bet_profit: CollateralToken
    total_simulated_amount: CollateralToken
    total_simulated_profit: CollateralToken
    roi: float
    simulated_roi: float
    sharpe_output_original: SharpeOutput
    sharpe_output_simulation: SharpeOutput
    maximize: float
