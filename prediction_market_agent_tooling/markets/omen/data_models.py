import typing as t
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel
from web3 import Web3

from prediction_market_agent_tooling.gtypes import (
    USD,
    ChecksumAddress,
    HexAddress,
    OmenOutcomeToken,
    Probability,
    Wei,
    xDai,
    HexBytes,
)
from prediction_market_agent_tooling.markets.data_models import (
    BetAmount,
    Currency,
    ProfitAmount,
    Resolution,
    ResolvedBet,
)
from prediction_market_agent_tooling.tools.utils import check_not_none
from prediction_market_agent_tooling.tools.web3_utils import wei_to_xdai

OMEN_TRUE_OUTCOME = "Yes"
OMEN_FALSE_OUTCOME = "No"
INVALID_ANSWER = 0xFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFF
OMEN_BASE_URL = "https://aiomen.eth.limo"


def get_boolean_outcome(outcome_str: str) -> bool:
    if outcome_str == OMEN_TRUE_OUTCOME:
        return True
    if outcome_str == OMEN_FALSE_OUTCOME:
        return False
    raise ValueError(f"Outcome `{outcome_str}` is not a valid boolean outcome.")


class Condition(BaseModel):
    id: HexBytes
    outcomeSlotCount: int

    @property
    def index_sets(self) -> t.List[int]:
        return [i + 1 for i in range(self.outcomeSlotCount)]


class Question(BaseModel):
    id: HexBytes
    title: str
    answerFinalizedTimestamp: t.Optional[datetime] = None
    currentAnswer: t.Optional[str] = None


class OmenPosition(BaseModel):
    id: HexBytes
    conditionIds: t.List[HexBytes]


class OmenUserPosition(BaseModel):
    id: HexBytes
    position: OmenPosition


class OmenMarket(BaseModel):
    """
    https://aiomen.eth.limo
    """

    BET_AMOUNT_CURRENCY: t.ClassVar[Currency] = Currency.xDai

    id: HexAddress
    title: str
    category: str
    collateralVolume: Wei
    usdVolume: USD
    collateralToken: HexAddress
    outcomes: list[str]
    outcomeTokenAmounts: list[OmenOutcomeToken]
    outcomeTokenMarginalPrices: t.Optional[list[xDai]]
    fee: t.Optional[Wei]
    resolutionTimestamp: t.Optional[int] = None
    answerFinalizedTimestamp: t.Optional[int] = None
    currentAnswer: t.Optional[str] = None
    creationTimestamp: t.Optional[int] = None
    condition: Condition
    question: Question

    @property
    def answer_index(self) -> t.Optional[int]:
        return int(self.currentAnswer, 16) if self.currentAnswer else None

    @property
    def has_valid_answer(self) -> bool:
        return self.answer_index is not None and self.answer_index != INVALID_ANSWER

    @property
    def is_open(self) -> bool:
        return self.currentAnswer is None

    @property
    def is_resolved(self) -> bool:
        return self.answerFinalizedTimestamp is not None and self.has_valid_answer

    @property
    def question_title(self) -> str:
        return self.title

    @property
    def creation_datetime(self) -> datetime | None:
        return (
            datetime.fromtimestamp(self.creationTimestamp)
            if self.creationTimestamp is not None
            else None
        )

    @property
    def finalized_datetime(self) -> datetime | None:
        return (
            datetime.fromtimestamp(self.answerFinalizedTimestamp)
            if self.answerFinalizedTimestamp is not None
            else None
        )

    @property
    def has_bonded_outcome(self) -> bool:
        return self.finalized_datetime is not None

    @property
    def market_maker_contract_address(self) -> HexAddress:
        return self.id

    @property
    def market_maker_contract_address_checksummed(self) -> ChecksumAddress:
        return Web3.to_checksum_address(self.market_maker_contract_address)

    @property
    def collateral_token_contract_address(self) -> HexAddress:
        return self.collateralToken

    @property
    def collateral_token_contract_address_checksummed(self) -> ChecksumAddress:
        return Web3.to_checksum_address(self.collateral_token_contract_address)

    @property
    def outcomeTokenProbabilities(self) -> t.Optional[list[Probability]]:
        return (
            [Probability(float(x)) for x in self.outcomeTokenMarginalPrices]
            if self.outcomeTokenMarginalPrices is not None
            else None
        )

    @property
    def p_no(self) -> Probability:
        return Probability(1 - self.p_yes)

    @property
    def p_yes(self) -> Probability:
        """
        Calculate the probability of the outcomes from the relative token amounts.

        Note, not all markets reliably have outcomeTokenMarginalPrices, hence we
        use the relative proportion of outcomeTokenAmounts to calculate the
        probabilities.

        The higher the proportion of available outcome tokens for a given outcome,
        the the lower the price of that token, and therefore the lower the
        probability of that outcome.
        """
        if self.outcomeTokenAmounts is None:
            raise ValueError(
                f"Market with title {self.title} has no outcomeTokenAmounts."
            )
        if len(self.outcomeTokenAmounts) != 2:
            raise ValueError(
                f"Market with title {self.title} has {len(self.outcomeTokenAmounts)} outcomes."
            )
        true_index = self.outcomes.index(OMEN_TRUE_OUTCOME)

        if sum(self.outcomeTokenAmounts) == 0:
            return Probability(0.5)

        return Probability(
            1 - self.outcomeTokenAmounts[true_index] / sum(self.outcomeTokenAmounts)
        )

    def __repr__(self) -> str:
        return f"Omen's market: {self.title}"

    @property
    def is_binary(self) -> bool:
        return len(self.outcomes) == 2

    @property
    def boolean_outcome(self) -> bool:
        if not self.is_binary:
            raise ValueError(
                f"Market with title {self.title} is not binary, it has {len(self.outcomes)} outcomes."
            )
        if not self.is_resolved:
            raise ValueError(f"Bet with title {self.title} is not resolved.")

        outcome: str = self.outcomes[check_not_none(self.answer_index)]
        return get_boolean_outcome(outcome)

    def get_resolution_enum(self) -> t.Optional[Resolution]:
        if not self.is_resolved:
            return None
        if self.boolean_outcome:
            return Resolution.YES
        else:
            return Resolution.NO

    @property
    def url(self) -> str:
        return f"{OMEN_BASE_URL}/#/{self.id}"


class OmenBetCreator(BaseModel):
    id: HexAddress


class OmenBet(BaseModel):
    id: HexAddress
    title: str
    collateralToken: HexAddress
    outcomeTokenMarginalPrice: xDai
    oldOutcomeTokenMarginalPrice: xDai
    type: str
    creator: OmenBetCreator
    creationTimestamp: int
    collateralAmount: Wei
    collateralAmountUSD: USD
    feeAmount: Wei
    outcomeIndex: int
    outcomeTokensTraded: int
    transactionHash: HexAddress
    fpmm: OmenMarket

    @property
    def creation_datetime(self) -> datetime:
        return datetime.fromtimestamp(self.creationTimestamp)

    @property
    def boolean_outcome(self) -> bool:
        return get_boolean_outcome(self.fpmm.outcomes[self.outcomeIndex])

    def get_profit(self) -> ProfitAmount:
        bet_amount_xdai = wei_to_xdai(self.collateralAmount)
        profit = (
            wei_to_xdai(Wei(self.outcomeTokensTraded)) - bet_amount_xdai
            if self.boolean_outcome == self.fpmm.boolean_outcome
            else -bet_amount_xdai
        )
        profit -= wei_to_xdai(self.feeAmount)
        return ProfitAmount(
            amount=profit,
            currency=Currency.xDai,
        )

    def to_generic_resolved_bet(self) -> ResolvedBet:
        if not self.fpmm.is_resolved:
            raise ValueError(
                f"Bet with title {self.title} is not resolved. It has no resolution time."
            )

        return ResolvedBet(
            amount=BetAmount(
                amount=Decimal(self.collateralAmountUSD), currency=Currency.xDai
            ),
            outcome=self.boolean_outcome,
            created_time=self.creation_datetime,
            market_question=self.title,
            market_outcome=self.fpmm.boolean_outcome,
            resolved_time=datetime.fromtimestamp(
                check_not_none(self.fpmm.answerFinalizedTimestamp)
            ),
            profit=self.get_profit(),
        )


class FixedProductMarketMakersData(BaseModel):
    fixedProductMarketMakers: list[OmenMarket]


class FixedProductMarketMakersResponse(BaseModel):
    data: FixedProductMarketMakersData


class RealityQuestion(BaseModel):
    id: str
    user: str
    historyHash: bytes
    updatedTimestamp: datetime
    questionId: bytes


class RealityAnswer(BaseModel):
    answer: str
    bondAggregate: Wei
    lastBond: Wei
    timestamp: datetime
    question: RealityQuestion


class RealityAnswers(BaseModel):
    answers: list[RealityAnswer]


class RealityAnswersResponse(BaseModel):
    data: RealityAnswers
