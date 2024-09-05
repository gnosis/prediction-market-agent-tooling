import typing as t
from datetime import datetime

from pydantic import BaseModel
from web3 import Web3

from prediction_market_agent_tooling.gtypes import (
    USD,
    ChecksumAddress,
    HexAddress,
    HexBytes,
    OmenOutcomeToken,
    Probability,
    Wei,
    xDai,
)
from prediction_market_agent_tooling.markets.data_models import (
    Bet,
    BetAmount,
    Currency,
    ProfitAmount,
    Resolution,
    ResolvedBet,
)
from prediction_market_agent_tooling.tools.utils import (
    check_not_none,
    should_not_happen,
)
from prediction_market_agent_tooling.tools.web3_utils import wei_to_xdai

OMEN_TRUE_OUTCOME = "Yes"
OMEN_FALSE_OUTCOME = "No"
INVALID_ANSWER = 0xFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFF
INVALID_ANSWER_HEX_BYTES = HexBytes(INVALID_ANSWER)
OMEN_BASE_URL = "https://aiomen.eth.limo"
PRESAGIO_BASE_URL = "https://presagio.pages.dev"


def get_boolean_outcome(outcome_str: str) -> bool:
    if outcome_str == OMEN_TRUE_OUTCOME:
        return True
    if outcome_str == OMEN_FALSE_OUTCOME:
        return False
    raise ValueError(f"Outcome `{outcome_str}` is not a valid boolean outcome.")


def get_bet_outcome(binary_outcome: bool) -> str:
    return OMEN_TRUE_OUTCOME if binary_outcome else OMEN_FALSE_OUTCOME


class Condition(BaseModel):
    id: HexBytes
    outcomeSlotCount: int

    @property
    def index_sets(self) -> t.List[int]:
        return [i + 1 for i in range(self.outcomeSlotCount)]


class Question(BaseModel):
    id: HexBytes
    title: str
    data: str
    templateId: int
    outcomes: list[str]
    isPendingArbitration: bool
    openingTimestamp: int
    answerFinalizedTimestamp: t.Optional[datetime] = None
    currentAnswer: t.Optional[str] = None

    @property
    def question_raw(self) -> str:
        # Based on https://github.com/protofire/omen-exchange/blob/2cfdf6bfe37afa8b169731d51fea69d42321d66c/app/src/hooks/graph/useGraphMarketMakerData.tsx#L217.
        return self.data

    @property
    def n_outcomes(self) -> int:
        return len(self.outcomes)

    @property
    def opening_datetime(self) -> datetime:
        return datetime.fromtimestamp(self.openingTimestamp)

    @property
    def has_answer(self) -> bool:
        return self.currentAnswer is not None

    @property
    def outcome_index(self) -> int | None:
        return (
            int(
                self.currentAnswer,
                16,
            )
            if self.currentAnswer is not None
            else None
        )

    @property
    def is_binary(self) -> bool:
        return len(self.outcomes) == 2

    @property
    def has_valid_answer(self) -> bool:
        return self.outcome_index is not None and self.outcome_index != INVALID_ANSWER

    @property
    def boolean_outcome(self) -> bool:
        if not self.is_binary:
            raise ValueError(
                f"Question with title {self.title} is not binary, it has {len(self.outcomes)} outcomes."
            )

        if not self.has_answer:
            raise ValueError(f"Question with title {self.title} is not answered.")

        outcome_index = check_not_none(self.outcome_index)

        if not self.has_valid_answer:
            raise ValueError(
                f"Question with title {self.title} has invalid answer {outcome_index}."
            )

        outcome: str = self.outcomes[outcome_index]
        return get_boolean_outcome(outcome)


class OmenPosition(BaseModel):
    id: HexBytes
    conditionIds: list[HexBytes]
    collateralTokenAddress: HexAddress
    indexSets: list[int]

    @property
    def condition_id(self) -> HexBytes:
        # I didn't find any example where this wouldn't hold, but keeping this double-check here in case something changes in the future.
        # May be the case if the market is created with multiple oracles.
        if len(self.conditionIds) != 1:
            raise ValueError(
                f"Bug in the logic, please investigate why zero or multiple conditions are returned for position {self.id=}"
            )
        return self.conditionIds[0]

    @property
    def index_set(self) -> int:
        if len(self.indexSets) != 1:
            raise ValueError(
                f"Bug in the logic, please investigate why zero or multiple index sets are returned for position {self.id=}"
            )
        return self.indexSets[0]

    @property
    def collateral_token_contract_address_checksummed(self) -> ChecksumAddress:
        return Web3.to_checksum_address(self.collateralTokenAddress)


class OmenUserPosition(BaseModel):
    id: HexBytes
    position: OmenPosition
    balance: Wei
    wrappedBalance: Wei
    totalBalance: Wei

    @property
    def redeemable(self) -> bool:
        return self.totalBalance > 0


class OmenMarket(BaseModel):
    """
    https://presagio.pages.dev

    An Omen market goes through the following stages:

    1. creation - can add liquidty immediately, and trade immediately if there is liquidity
    2. closing - market is closed, and a question is simultaneously opened for answers on Reality
    3. finalizing - the question is finalized on reality (including any disputes)
    4. resolving - a manual step required by calling the Omen oracle contract
    5. redeeming - a user withdraws collateral tokens from the market
    """

    BET_AMOUNT_CURRENCY: t.ClassVar[Currency] = Currency.xDai

    id: HexAddress
    title: str
    creator: HexAddress
    category: str
    collateralVolume: Wei
    # Note: there are two similar parameters relating to liquidity:
    # liquidityParameter and liquidityMeasure. The former appears to match most
    # closely with the liquidity returned when calling the contract directly
    # (see OmenAgentMarket.get_liquidity). So we can use it e.g. for filtering
    # markets, but until better understood, please call the contract directly.
    liquidityParameter: Wei
    usdVolume: USD
    collateralToken: HexAddress
    outcomes: list[str]
    outcomeTokenAmounts: list[OmenOutcomeToken]
    outcomeTokenMarginalPrices: t.Optional[list[xDai]]
    fee: t.Optional[Wei]
    resolutionTimestamp: t.Optional[int] = None
    answerFinalizedTimestamp: t.Optional[int] = None
    currentAnswer: t.Optional[HexBytes] = None
    creationTimestamp: int
    condition: Condition
    question: Question
    lastActiveDay: int
    lastActiveHour: int

    @property
    def openingTimestamp(self) -> int:
        # This field is also available on this model itself, but for some reason it's typed to be optional,
        # but Question's openingTimestamp is typed to be always present, so use that one instead.
        return self.question.openingTimestamp

    @property
    def opening_datetime(self) -> datetime:
        return datetime.fromtimestamp(self.openingTimestamp)

    @property
    def close_time(self) -> datetime:
        # Opening of the Reality's question is close time for the market,
        # however, market is usually "closed" even sooner by removing all the liquidity.
        return self.opening_datetime

    @property
    def answer_index(self) -> t.Optional[int]:
        return self.currentAnswer.as_int() if self.currentAnswer else None

    @property
    def has_valid_answer(self) -> bool:
        return self.answer_index is not None and self.answer_index != INVALID_ANSWER

    @property
    def is_open(self) -> bool:
        return self.currentAnswer is None

    @property
    def is_resolved(self) -> bool:
        return (
            # Finalized on Realitio (e.g. 24h has passed since the last answer was submitted)
            self.answerFinalizedTimestamp is not None
            # Resolved on Oracle (e.g. resolved after it was finalized)
            and self.resolutionTimestamp is not None
        )

    @property
    def is_resolved_with_valid_answer(self) -> bool:
        return self.is_resolved and self.has_valid_answer

    @property
    def question_title(self) -> str:
        return self.title

    @property
    def creation_datetime(self) -> datetime:
        return datetime.fromtimestamp(self.creationTimestamp)

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
    def yes_index(self) -> int:
        return self.outcomes.index(OMEN_TRUE_OUTCOME)

    @property
    def no_index(self) -> int:
        return self.outcomes.index(OMEN_FALSE_OUTCOME)

    @property
    def current_p_no(self) -> Probability:
        return Probability(1 - self.current_p_yes)

    @property
    def current_p_yes(self) -> Probability:
        """
        Calculate the probability of the outcomes from the relative token amounts.

        Note, not all markets reliably have outcomeTokenMarginalPrices, hence we
        use the relative proportion of outcomeTokenAmounts to calculate the
        probabilities.

        The higher the proportion of available outcome tokens for a given outcome,
        the the lower the price of that token, and therefore the lower the
        probability of that outcome.
        """
        if len(self.outcomeTokenAmounts) != 2:
            raise ValueError(
                f"Market with title {self.title} has {len(self.outcomeTokenAmounts)} outcomes."
            )

        if sum(self.outcomeTokenAmounts) == 0:
            # If there are no outcome tokens, it should mean that market is closed and without liquidity, so we need to infer the probabilities based on the answer.
            return (
                Probability(1.0)
                if self.yes_index == self.answer_index
                else (
                    Probability(0.0)
                    if self.no_index == self.answer_index
                    else (
                        Probability(0.5)
                        if not self.has_valid_answer  # Invalid market or closed market without resolution.
                        else should_not_happen("Unknown condition.")
                    )
                )
            )

        return Probability(
            1 - self.outcomeTokenAmounts[self.yes_index] / sum(self.outcomeTokenAmounts)
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
        if not self.is_resolved_with_valid_answer:
            raise ValueError(f"Bet with title {self.title} is not resolved.")

        outcome: str = self.outcomes[check_not_none(self.answer_index)]
        return get_boolean_outcome(outcome)

    def get_resolution_enum(self) -> t.Optional[Resolution]:
        if not self.is_resolved_with_valid_answer:
            return None
        if self.boolean_outcome:
            return Resolution.YES
        else:
            return Resolution.NO

    @property
    def url(self) -> str:
        return f"{PRESAGIO_BASE_URL}/markets?id={self.id}"


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
    outcomeTokensTraded: Wei
    transactionHash: HexAddress
    fpmm: OmenMarket

    @property
    def creation_datetime(self) -> datetime:
        return datetime.fromtimestamp(self.creationTimestamp)

    @property
    def boolean_outcome(self) -> bool:
        return get_boolean_outcome(self.fpmm.outcomes[self.outcomeIndex])

    @property
    def old_probability(self) -> Probability:
        # Old marginal price is the probability of the outcome before placing this bet.
        return Probability(float(self.oldOutcomeTokenMarginalPrice))

    @property
    def probability(self) -> Probability:
        # Marginal price is the probability of the outcome after placing this bet.
        return Probability(float(self.outcomeTokenMarginalPrice))

    def get_profit(self) -> ProfitAmount:
        bet_amount_xdai = wei_to_xdai(self.collateralAmount)
        profit = (
            wei_to_xdai(self.outcomeTokensTraded) - bet_amount_xdai
            if self.boolean_outcome == self.fpmm.boolean_outcome
            else -bet_amount_xdai
        )
        profit -= wei_to_xdai(self.feeAmount)
        return ProfitAmount(
            amount=profit,
            currency=Currency.xDai,
        )

    def to_bet(self) -> Bet:
        return Bet(
            amount=BetAmount(amount=self.collateralAmountUSD, currency=Currency.xDai),
            outcome=self.boolean_outcome,
            created_time=self.creation_datetime,
            market_question=self.title,
            market_id=self.fpmm.id,
        )

    def to_generic_resolved_bet(self) -> ResolvedBet:
        if not self.fpmm.is_resolved_with_valid_answer:
            raise ValueError(
                f"Bet with title {self.title} is not resolved. It has no resolution time."
            )

        return ResolvedBet(
            amount=BetAmount(amount=self.collateralAmountUSD, currency=Currency.xDai),
            outcome=self.boolean_outcome,
            created_time=self.creation_datetime,
            market_question=self.title,
            market_id=self.fpmm.id,
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
    # This `id` is in form of `0x79e32ae03fb27b07c89c0c568f80287c01ca2e57-0x2d362f435e7b5159794ff0b5457a900283fca41fe6301dc855a647595903db13`,
    # which I couldn't find how it is created, but based on how it looks like I assume it's composed of `answerId-questionId`.
    # (Why is answer id as part of the question object? Because this question object is actually received from the answer object below).
    # And because all the contract methods so far needed bytes32 input, when asked for question id, `questionId` field was the correct one to use so far.
    id: str
    user: HexAddress
    historyHash: HexBytes | None
    updatedTimestamp: datetime
    contentHash: HexBytes
    questionId: HexBytes
    answerFinalizedTimestamp: datetime
    currentScheduledFinalizationTimestamp: datetime

    @property
    def url(self) -> str:
        return f"https://reality.eth.limo/app/#!/question/{self.id}"


class RealityAnswer(BaseModel):
    id: str
    timestamp: datetime
    answer: HexBytes
    lastBond: Wei
    bondAggregate: Wei
    question: RealityQuestion
    createdBlock: int


class RealityResponse(BaseModel):
    """
    This is similar to `RealityAnswer`, but contains additional fields, most importantly `historyHash`.
    """

    id: str
    timestamp: datetime
    answer: HexBytes
    isUnrevealed: bool
    isCommitment: bool
    bond: Wei
    user: HexAddress
    historyHash: HexBytes
    question: RealityQuestion
    createdBlock: int
    revealedBlock: int | None

    @property
    def bond_xdai(self) -> xDai:
        return wei_to_xdai(self.bond)

    @property
    def user_checksummed(self) -> ChecksumAddress:
        return Web3.to_checksum_address(self.user)


class RealityAnswers(BaseModel):
    answers: list[RealityAnswer]


class RealityAnswersResponse(BaseModel):
    data: RealityAnswers
