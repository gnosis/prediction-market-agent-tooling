from enum import Enum
from typing import Annotated, Any, Sequence

from pydantic import BaseModel, BeforeValidator, computed_field, model_validator

from prediction_market_agent_tooling.deploy.constants import (
    DOWN_OUTCOME_LOWERCASE_IDENTIFIER,
    INVALID_OUTCOME_LOWERCASE_IDENTIFIER,
    NO_OUTCOME_LOWERCASE_IDENTIFIER,
    UP_OUTCOME_LOWERCASE_IDENTIFIER,
    YES_OUTCOME_LOWERCASE_IDENTIFIER,
)
from prediction_market_agent_tooling.gtypes import (
    USD,
    CollateralToken,
    OutcomeStr,
    OutcomeToken,
    Probability,
    Wei,
)
from prediction_market_agent_tooling.logprobs_parser import FieldLogprobs
from prediction_market_agent_tooling.markets.omen.omen_constants import (
    OMEN_FALSE_OUTCOME,
    OMEN_TRUE_OUTCOME,
)
from prediction_market_agent_tooling.tools.utils import DatetimeUTC, check_not_none


class Resolution(BaseModel):
    outcome: OutcomeStr | None
    invalid: bool

    @staticmethod
    def from_answer(answer: OutcomeStr) -> "Resolution":
        return Resolution(outcome=answer, invalid=False)

    def find_outcome_matching_market(
        self, market_outcomes: Sequence[OutcomeStr]
    ) -> OutcomeStr | None:
        """
        Finds a matching outcome in the provided market outcomes.

        Performs case-insensitive matching between this resolution's outcome
        and the provided market outcomes.

        """

        if not self.outcome:
            return None

        normalized_outcome = self.outcome.lower()
        for outcome in market_outcomes:
            if outcome.lower() == normalized_outcome:
                return outcome
        return None


class Bet(BaseModel):
    id: str
    amount: CollateralToken
    outcome: OutcomeStr
    created_time: DatetimeUTC
    market_question: str
    market_id: str

    def __str__(self) -> str:
        return f"Bet for market {self.market_id} for question {self.market_question} created at {self.created_time}: {self.amount} on {self.outcome}"


class ResolvedBet(Bet):
    market_outcome: OutcomeStr
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


class ScalarProbabilisticAnswer(BaseModel):
    scalar_value: Wei
    upperBound: Wei
    lowerBound: Wei
    confidence: float
    reasoning: str | None = None
    logprobs: list[FieldLogprobs] | None = None

    @property
    def p_up(self) -> Probability:
        if self.scalar_value > self.upperBound:
            return Probability(1)
        elif self.scalar_value < self.lowerBound:
            return Probability(0)
        else:
            return Probability(
                (self.scalar_value - self.lowerBound)
                / (self.upperBound - self.lowerBound)
            )

    @property
    def p_down(self) -> Probability:
        return Probability(1 - self.p_up)


class ProbabilisticAnswer(BaseModel):
    p_yes: Probability
    confidence: float
    reasoning: str | None = None
    logprobs: list[FieldLogprobs] | None = None

    @property
    def p_no(self) -> Probability:
        return Probability(1 - self.p_yes)

    @property
    def probable_resolution(self) -> Resolution:
        return (
            Resolution(
                outcome=OutcomeStr(YES_OUTCOME_LOWERCASE_IDENTIFIER), invalid=False
            )
            if self.p_yes > 0.5
            else Resolution(
                outcome=OutcomeStr(NO_OUTCOME_LOWERCASE_IDENTIFIER), invalid=False
            )
        )


class CategoricalProbabilisticAnswer(BaseModel):
    probabilities: dict[OutcomeStr, Probability]
    confidence: float
    reasoning: str | None = None

    @model_validator(mode="before")
    @classmethod
    def _model_validator(cls, data: Any) -> Any:
        if "p_yes" in data:
            return CategoricalProbabilisticAnswer.from_probabilistic_answer(
                ProbabilisticAnswer.model_validate(data)
            ).model_dump()
        return data

    @property
    def probable_resolution(self) -> Resolution:
        most_likely_outcome = max(
            self.probabilities.items(),
            key=lambda item: item[1],
        )[0]
        return Resolution(outcome=most_likely_outcome, invalid=False)

    def to_probabilistic_answer(self) -> ProbabilisticAnswer:
        p_yes = check_not_none(self.get_yes_probability())
        return ProbabilisticAnswer(
            p_yes=p_yes,
            confidence=self.confidence,
        )

    @staticmethod
    def from_probabilistic_answer(
        answer: ProbabilisticAnswer,
        market_outcomes: Sequence[OutcomeStr] | None = None,
    ) -> "CategoricalProbabilisticAnswer":
        return CategoricalProbabilisticAnswer(
            probabilities={
                (
                    OMEN_TRUE_OUTCOME
                    if market_outcomes and OMEN_TRUE_OUTCOME in market_outcomes
                    else OutcomeStr(YES_OUTCOME_LOWERCASE_IDENTIFIER)
                ): answer.p_yes,
                (
                    OMEN_FALSE_OUTCOME
                    if market_outcomes and OMEN_FALSE_OUTCOME in market_outcomes
                    else OutcomeStr(NO_OUTCOME_LOWERCASE_IDENTIFIER)
                ): Probability(1 - answer.p_yes),
            },
            confidence=answer.confidence,
            reasoning=answer.reasoning,
        )

    @staticmethod
    def from_scalar_answer(
        answer: ScalarProbabilisticAnswer,
        market_outcomes: Sequence[OutcomeStr],
    ) -> "CategoricalProbabilisticAnswer":
        probabilities = {}
        lowercase_market_outcomes = [outcome.lower() for outcome in market_outcomes]

        if not set(
            [
                DOWN_OUTCOME_LOWERCASE_IDENTIFIER,
                UP_OUTCOME_LOWERCASE_IDENTIFIER,
            ]
        ).issubset(lowercase_market_outcomes):
            raise ValueError("Market with no outcomes")

        probabilities[OutcomeStr(UP_OUTCOME_LOWERCASE_IDENTIFIER.upper())] = answer.p_up
        probabilities[
            OutcomeStr(DOWN_OUTCOME_LOWERCASE_IDENTIFIER.upper())
        ] = answer.p_down

        if (
            market_outcomes
            and INVALID_OUTCOME_LOWERCASE_IDENTIFIER in lowercase_market_outcomes
        ):
            probabilities[
                OutcomeStr(INVALID_OUTCOME_LOWERCASE_IDENTIFIER.capitalize())
            ] = Probability(1 - answer.p_up - answer.p_down)

        return CategoricalProbabilisticAnswer(
            probabilities=probabilities,
            confidence=answer.confidence,
            reasoning=answer.reasoning,
        )

    def probability_for_market_outcome(self, market_outcome: OutcomeStr) -> Probability:
        for k, v in self.probabilities.items():
            if k.lower() == market_outcome.lower():
                return v
        raise ValueError(
            f"Could not find probability for market outcome {market_outcome}"
        )

    def get_yes_probability(self) -> Probability | None:
        return next(
            (
                p
                for o, p in self.probabilities.items()
                if o.lower() == YES_OUTCOME_LOWERCASE_IDENTIFIER
            ),
            None,
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
    outcome: OutcomeStr
    amount: USD

    @model_validator(mode="before")
    @classmethod
    def _model_validator(cls, data: Any) -> Any:
        if isinstance(data["outcome"], bool):
            data["outcome"] = (
                YES_OUTCOME_LOWERCASE_IDENTIFIER
                if data["outcome"]
                else NO_OUTCOME_LOWERCASE_IDENTIFIER
            )
        return data


class PlacedTrade(Trade):
    id: str

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
    probabilities: dict[OutcomeStr, Probability]
    agent_prob_multi: dict[OutcomeStr, Probability]
    agent_conf: float
    org_bet: CollateralToken
    sim_bet: CollateralToken
    org_dir: OutcomeStr
    sim_dir: OutcomeStr
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
    maximize: float
