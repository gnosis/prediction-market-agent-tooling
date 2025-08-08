import typing as t

from pydantic import BaseModel, ConfigDict, Field, computed_field, model_validator
from web3 import Web3

from prediction_market_agent_tooling.gtypes import (
    USD,
    ChecksumAddress,
    CollateralToken,
    HexAddress,
    HexBytes,
    HexStr,
    OutcomeStr,
    OutcomeWei,
    Probability,
    Wei,
    xDai,
    xDaiWei,
)
from prediction_market_agent_tooling.loggers import logger
from prediction_market_agent_tooling.markets.data_models import (
    Bet,
    Resolution,
    ResolvedBet,
)
from prediction_market_agent_tooling.markets.omen.omen_constants import (
    OMEN_FALSE_OUTCOME,
    OMEN_TRUE_OUTCOME,
)
from prediction_market_agent_tooling.tools.contract import (
    ContractERC20OnGnosisChain,
    init_collateral_token_contract,
    to_gnosis_chain_contract,
)
from prediction_market_agent_tooling.tools.tokens.usd import get_token_in_usd
from prediction_market_agent_tooling.tools.utils import (
    BPS_CONSTANT,
    DatetimeUTC,
    check_not_none,
    should_not_happen,
    utcnow,
)

OMEN_BINARY_MARKET_OUTCOMES: t.Sequence[OutcomeStr] = [
    OMEN_TRUE_OUTCOME,
    OMEN_FALSE_OUTCOME,
]
INVALID_ANSWER = 0xFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFF
INVALID_ANSWER_HEX_BYTES = HexBytes(INVALID_ANSWER)
INVALID_ANSWER_STR = HexStr(INVALID_ANSWER_HEX_BYTES.hex())
OMEN_BASE_URL = "https://aiomen.eth.limo"
PRESAGIO_BASE_URL = "https://presagio.pages.dev"
TEST_CATEGORY = "test"  # This category is hidden on Presagio for testing purposes.


def construct_presagio_url(market_id: HexAddress) -> str:
    return f"{PRESAGIO_BASE_URL}/markets?id={market_id}"


def get_boolean_outcome(outcome_str: str) -> bool:
    if outcome_str == OMEN_TRUE_OUTCOME:
        return True
    if outcome_str == OMEN_FALSE_OUTCOME:
        return False
    raise ValueError(f"Outcome `{outcome_str}` is not a valid boolean outcome.")


def get_bet_outcome(binary_outcome: bool) -> OutcomeStr:
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
    outcomes: t.Sequence[OutcomeStr]
    isPendingArbitration: bool
    openingTimestamp: int
    answerFinalizedTimestamp: t.Optional[DatetimeUTC] = None
    currentAnswer: t.Optional[str] = None

    @property
    def question_id(self) -> HexBytes:
        return self.id

    @property
    def question_raw(self) -> str:
        # Based on https://github.com/protofire/omen-exchange/blob/2cfdf6bfe37afa8b169731d51fea69d42321d66c/app/src/hooks/graph/useGraphMarketMakerData.tsx#L217.
        return self.data

    @property
    def n_outcomes(self) -> int:
        return len(self.outcomes)

    @property
    def opening_datetime(self) -> DatetimeUTC:
        return DatetimeUTC.to_datetime_utc(self.openingTimestamp)

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

    def get_collateral_token_contract(
        self, web3: Web3 | None = None
    ) -> ContractERC20OnGnosisChain:
        web3 = web3 or ContractERC20OnGnosisChain.get_web3()
        return to_gnosis_chain_contract(
            init_collateral_token_contract(
                self.collateral_token_contract_address_checksummed, web3
            )
        )


class OmenUserPosition(BaseModel):
    id: HexBytes
    position: OmenPosition
    balance: OutcomeWei
    wrappedBalance: OutcomeWei
    totalBalance: OutcomeWei

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
    outcomes: t.Sequence[OutcomeStr]
    outcomeTokenAmounts: list[OutcomeWei]
    outcomeTokenMarginalPrices: t.Optional[list[CollateralToken]]
    fee: t.Optional[Wei]
    resolutionTimestamp: t.Optional[int] = None
    answerFinalizedTimestamp: t.Optional[int] = None
    currentAnswer: t.Optional[HexBytes] = None
    creationTimestamp: int
    condition: Condition
    question: Question

    @model_validator(mode="after")
    def _model_validator(self) -> "OmenMarket":
        if any(number < 0 for number in self.outcomeTokenAmounts):
            # Sometimes we receive markets with outcomeTokenAmounts as `model.outcomeTokenAmounts=[OutcomeWei(24662799387878572), OutcomeWei(-24750000000000000)]`,
            # which should be impossible.
            # Current huntch is that it's a weird transitional status or bug after withdrawing liquidity.
            # Because so far, it always happened on markets with withdrawn liquidity,
            # so we just set them to zeros, as we expect them to be.
            logger.warning(
                f"Market {self.url} has invalid {self.outcomeTokenAmounts=}. Setting them to zeros."
            )
            self.outcomeTokenAmounts = [OutcomeWei(0) for _ in self.outcomes]
            self.outcomeTokenMarginalPrices = None
            self.liquidityParameter = Wei(0)

        return self

    @property
    def openingTimestamp(self) -> int:
        # This field is also available on this model itself, but for some reason it's typed to be optional,
        # but Question's openingTimestamp is typed to be always present, so use that one instead.
        return self.question.openingTimestamp

    @property
    def opening_datetime(self) -> DatetimeUTC:
        return DatetimeUTC.to_datetime_utc(self.openingTimestamp)

    @property
    def close_time(self) -> DatetimeUTC:
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
        return self.close_time > utcnow()

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
    def creation_datetime(self) -> DatetimeUTC:
        return DatetimeUTC.to_datetime_utc(self.creationTimestamp)

    @property
    def finalized_datetime(self) -> DatetimeUTC | None:
        return (
            DatetimeUTC.to_datetime_utc(self.answerFinalizedTimestamp)
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
            1
            - (
                self.outcomeTokenAmounts[self.yes_index]
                / sum(self.outcomeTokenAmounts, start=OutcomeWei(0))
            )
        )

    def __repr__(self) -> str:
        return f"Omen's market: {self.title}"

    @property
    def is_binary(self) -> bool:
        return len(self.outcomes) == 2

    def outcome_from_answer(self, answer: HexBytes) -> OutcomeStr | None:
        if answer == INVALID_ANSWER_HEX_BYTES:
            return None
        return self.outcomes[answer.as_int()]

    def get_resolution_enum_from_answer(self, answer: HexBytes) -> Resolution:
        if outcome := self.outcome_from_answer(answer):
            return Resolution.from_answer(outcome)

        return Resolution(outcome=None, invalid=True)

    def get_resolution_enum(self) -> t.Optional[Resolution]:
        if not self.is_resolved_with_valid_answer:
            return None
        return self.get_resolution_enum_from_answer(
            check_not_none(
                self.currentAnswer, "Can not be None if `is_resolved_with_valid_answer`"
            )
        )

    @property
    def url(self) -> str:
        return construct_presagio_url(self.id)

    @staticmethod
    def from_created_market(model: "CreatedMarket") -> "OmenMarket":
        """
        OmenMarket is meant to be retrieved from subgraph, however in tests against local chain it's very handy to create it out of `CreatedMarket`,
        which is collection of events that are emitted during the market creation in omen_create_market_tx function.
        """
        if len(model.market_event.conditionIds) != 1:
            raise ValueError(
                f"Unexpected number of conditions: {len(model.market_event.conditionIds)}"
            )
        outcome_token_amounts = model.funding_event.outcome_token_amounts
        return OmenMarket(
            id=HexAddress(
                HexStr(model.market_event.fixedProductMarketMaker.lower())
            ),  # Lowering to be identical with subgraph's output.
            title=model.question_event.parsed_question.question,
            creator=HexAddress(
                HexStr(model.market_event.creator.lower())
            ),  # Lowering to be identical with subgraph's output.
            category=model.question_event.parsed_question.category,
            collateralVolume=Wei(0),  # No volume possible yet.
            liquidityParameter=calculate_liquidity_parameter(outcome_token_amounts),
            usdVolume=USD(0),  # No volume possible yet.
            fee=model.fee,
            collateralToken=HexAddress(
                HexStr(model.market_event.collateralToken.lower())
            ),  # Lowering to be identical with subgraph's output.
            outcomes=model.question_event.parsed_question.outcomes,
            outcomeTokenAmounts=outcome_token_amounts,
            outcomeTokenMarginalPrices=calculate_marginal_prices(outcome_token_amounts),
            answerFinalizedTimestamp=None,  # It's a fresh market.
            currentAnswer=None,  # It's a fresh market.
            creationTimestamp=model.market_creation_timestamp,
            condition=Condition(
                id=model.market_event.conditionIds[0],
                outcomeSlotCount=len(model.question_event.parsed_question.outcomes),
            ),
            question=Question(
                id=model.question_event.question_id,
                title=model.question_event.parsed_question.question,
                data=model.question_event.question,  # Question in the event holds the "raw" data.
                templateId=model.question_event.template_id,
                outcomes=model.question_event.parsed_question.outcomes,
                isPendingArbitration=False,  # Can not be, it's a fresh market.
                openingTimestamp=model.question_event.opening_ts,
                answerFinalizedTimestamp=None,  # It's a new one, can not be.
                currentAnswer=None,  # It's a new one, no answer yet.
            ),
        )


def calculate_liquidity_parameter(
    outcome_token_amounts: list[OutcomeWei],
) -> Wei:
    """
    Converted to Python from https://github.com/protofire/omen-subgraph/blob/f92bbfb6fa31ed9cd5985c416a26a2f640837d8b/src/utils/fpmm.ts#L171.
    """
    amounts_product = Wei(1)
    for amount in outcome_token_amounts:
        amounts_product *= amount.as_wei
    n = len(outcome_token_amounts)
    liquidity_parameter = amounts_product.value ** (1.0 / n)
    return Wei(liquidity_parameter)


def calculate_marginal_prices(
    outcome_token_amounts: list[OutcomeWei],
) -> list[CollateralToken] | None:
    """
    Converted to Python from https://github.com/protofire/omen-subgraph/blob/f92bbfb6fa31ed9cd5985c416a26a2f640837d8b/src/utils/fpmm.ts#L197.
    """
    all_non_zero = all(x != 0 for x in outcome_token_amounts)
    if not all_non_zero:
        return None

    n_outcomes = len(outcome_token_amounts)
    weights: list[Wei] = []

    for i in range(n_outcomes):
        weight = Wei(1)
        for j in range(n_outcomes):
            if i != j:
                weight *= outcome_token_amounts[j].as_wei.value
        weights.append(weight)

    sum_weights = sum(weights, start=Wei(0))

    marginal_prices = [weights[i].value / sum_weights.value for i in range(n_outcomes)]
    return [CollateralToken(mp) for mp in marginal_prices]


class OmenBetCreator(BaseModel):
    id: HexAddress


class OmenBet(BaseModel):
    id: HexAddress  # A concatenation of: FPMM contract ID, trader ID and nonce. See https://github.com/protofire/omen-subgraph/blob/f92bbfb6fa31ed9cd5985c416a26a2f640837d8b/src/FixedProductMarketMakerMapping.ts#L109
    title: str
    collateralToken: HexAddress
    outcomeTokenMarginalPrice: CollateralToken
    oldOutcomeTokenMarginalPrice: CollateralToken
    type: str
    creator: OmenBetCreator
    creationTimestamp: int
    collateralAmount: Wei
    feeAmount: Wei
    outcomeIndex: int
    outcomeTokensTraded: OutcomeWei
    transactionHash: HexBytes
    fpmm: OmenMarket

    @property
    def collateral_amount_token(self) -> CollateralToken:
        return self.collateralAmount.as_token

    @property
    def collateral_token_checksummed(self) -> ChecksumAddress:
        return Web3.to_checksum_address(self.collateralToken)

    @property
    def creation_datetime(self) -> DatetimeUTC:
        return DatetimeUTC.to_datetime_utc(self.creationTimestamp)

    @property
    def old_probability(self) -> Probability:
        # Old marginal price is the probability of the outcome before placing this bet.
        return Probability(float(self.oldOutcomeTokenMarginalPrice))

    @property
    def probability(self) -> Probability:
        # Marginal price is the probability of the outcome after placing this bet.
        return Probability(float(self.outcomeTokenMarginalPrice))

    def get_collateral_amount_usd(self) -> USD:
        return get_token_in_usd(
            self.collateral_amount_token, self.collateral_token_checksummed
        )

    def get_profit(self) -> CollateralToken:
        bet_amount = self.collateral_amount_token

        if not self.fpmm.has_valid_answer:
            return CollateralToken(0)

        profit = (
            self.outcomeTokensTraded.as_outcome_token.as_token - bet_amount
            if self.outcomeIndex == self.fpmm.answer_index
            else -bet_amount
        )
        return profit

    def to_bet(self) -> Bet:
        return Bet(
            id=str(self.transactionHash),
            # Use the transaction hash instead of the bet id - both are valid, but we return the transaction hash from the trade functions, so be consistent here.
            amount=self.collateral_amount_token,
            outcome=self.fpmm.outcomes[self.outcomeIndex],
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
            id=self.transactionHash.hex(),
            # Use the transaction hash instead of the bet id - both are valid, but we return the transaction hash from the trade functions, so be consistent here.
            amount=self.collateral_amount_token,
            outcome=self.fpmm.outcomes[self.outcomeIndex],
            created_time=self.creation_datetime,
            market_question=self.title,
            market_id=self.fpmm.id,
            market_outcome=self.fpmm.outcomes[
                check_not_none(
                    self.fpmm.answer_index,
                    "Should not be None if `is_resolved_with_valid_answer`.",
                )
            ],
            resolved_time=check_not_none(self.fpmm.finalized_datetime),
            profit=self.get_profit(),
        )


class FixedProductMarketMakersData(BaseModel):
    fixedProductMarketMakers: list[OmenMarket]


class FixedProductMarketMakersResponse(BaseModel):
    data: FixedProductMarketMakersData


class RealityQuestion(BaseModel):
    # This `id` is in form of `0x79e32ae03fb27b07c89c0c568f80287c01ca2e57-0x2d362f435e7b5159794ff0b5457a900283fca41fe6301dc855a647595903db13`, # web3-private-key-ok
    # which I couldn't find how it is created, but based on how it looks like I assume it's composed of `answerId-questionId`.
    # (Why is answer id as part of the question object? Because this question object is actually received from the answer object below).
    # And because all the contract methods so far needed bytes32 input, when asked for question id, `questionId` field was the correct one to use so far.
    id: str
    user: HexAddress
    historyHash: HexBytes | None
    updatedTimestamp: int
    contentHash: HexBytes
    questionId: HexBytes  # This is the `id` on question from omen subgraph.
    answerFinalizedTimestamp: int | None
    currentScheduledFinalizationTimestamp: int

    @property
    def updated_datetime(self) -> DatetimeUTC:
        return DatetimeUTC.to_datetime_utc(self.updatedTimestamp)

    @property
    def answer_finalized_datetime(self) -> DatetimeUTC | None:
        return (
            DatetimeUTC.to_datetime_utc(self.answerFinalizedTimestamp)
            if self.answerFinalizedTimestamp is not None
            else None
        )

    @property
    def current_scheduled_finalization_datetime(self) -> DatetimeUTC:
        return DatetimeUTC.to_datetime_utc(self.currentScheduledFinalizationTimestamp)

    @property
    def url(self) -> str:
        return f"https://reality.eth.limo/app/#!/question/{self.id}"


class RealityAnswer(BaseModel):
    id: str
    timestamp: int
    answer: HexBytes
    lastBond: Wei
    bondAggregate: Wei
    question: RealityQuestion
    createdBlock: int

    @property
    def timestamp_datetime(self) -> DatetimeUTC:
        return DatetimeUTC.to_datetime_utc(self.timestamp)


class RealityResponse(BaseModel):
    """
    This is similar to `RealityAnswer`, but contains additional fields, most importantly `historyHash`.
    """

    id: str
    timestamp: int
    answer: HexBytes
    isUnrevealed: bool
    isCommitment: bool
    bond: xDaiWei
    user: HexAddress
    historyHash: HexBytes
    question: RealityQuestion
    createdBlock: int
    revealedBlock: int | None

    @property
    def bond_xdai(self) -> xDai:
        return self.bond.as_xdai

    @property
    def user_checksummed(self) -> ChecksumAddress:
        return Web3.to_checksum_address(self.user)


class RealityAnswers(BaseModel):
    answers: list[RealityAnswer]


class RealityAnswersResponse(BaseModel):
    data: RealityAnswers


def format_realitio_question(
    question: str,
    outcomes: t.Sequence[str],
    category: str,
    language: str,
    template_id: int,
) -> str:
    """If you add a new template id here, also add to the parsing function below."""

    # Escape characters for JSON troubles on Reality.eth.
    question = question.replace('"', '\\"')

    if template_id == 2:
        return "␟".join(
            [
                question,
                ",".join(f'"{o}"' for o in outcomes),
                category,
                language,
            ]
        )

    raise ValueError(f"Unsupported template id {template_id}.")


def parse_realitio_question(question_raw: str, template_id: int) -> "ParsedQuestion":
    """If you add a new template id here, also add to the encoding function above."""
    if template_id == 2:
        question, outcomes_raw, category, language = question_raw.split("␟")
        outcomes = [OutcomeStr(o.strip('"')) for o in outcomes_raw.split(",")]
        return ParsedQuestion(
            question=question, outcomes=outcomes, category=category, language=language
        )

    raise ValueError(f"Unsupported template id {template_id}.")


class ParsedQuestion(BaseModel):
    question: str
    outcomes: t.Sequence[OutcomeStr]
    language: str
    category: str


class RealitioLogNewQuestionEvent(BaseModel):
    question_id: HexBytes
    user: HexAddress
    template_id: int
    question: str  # Be aware, this is question in format of format_realitio_question function, it's raw data.
    content_hash: HexBytes
    arbitrator: HexAddress
    timeout: int
    opening_ts: int
    nonce: int
    created: int

    @property
    def user_checksummed(self) -> ChecksumAddress:
        return Web3.to_checksum_address(self.user)

    @property
    def parsed_question(self) -> ParsedQuestion:
        return parse_realitio_question(
            question_raw=self.question, template_id=self.template_id
        )


class OmenFixedProductMarketMakerCreationEvent(BaseModel):
    creator: HexAddress
    fixedProductMarketMaker: HexAddress
    conditionalTokens: HexAddress
    collateralToken: HexAddress
    conditionIds: list[HexBytes]
    fee: int

    @property
    def creator_checksummed(self) -> ChecksumAddress:
        return Web3.to_checksum_address(self.creator)

    @property
    def fixed_product_market_maker_checksummed(self) -> ChecksumAddress:
        return Web3.to_checksum_address(self.fixedProductMarketMaker)

    @property
    def conditional_tokens_checksummed(self) -> ChecksumAddress:
        return Web3.to_checksum_address(self.conditionalTokens)

    @property
    def collateral_token_checksummed(self) -> ChecksumAddress:
        return Web3.to_checksum_address(self.collateralToken)


class ConditionPreparationEvent(BaseModel):
    conditionId: HexBytes
    oracle: HexAddress
    questionId: HexBytes
    outcomeSlotCount: int


class FPMMFundingAddedEvent(BaseModel):
    funder: HexAddress
    amountsAdded: list[Wei]
    sharesMinted: Wei

    @property
    def outcome_token_amounts(self) -> list[OutcomeWei]:
        # Just renaming so we remember what it is.
        return [OutcomeWei(x.value) for x in self.amountsAdded]


class CreatedMarket(BaseModel):
    market_creation_timestamp: int
    market_event: OmenFixedProductMarketMakerCreationEvent
    funding_event: FPMMFundingAddedEvent
    condition_id: HexBytes
    question_event: RealitioLogNewQuestionEvent
    condition_event: ConditionPreparationEvent | None
    initial_funds: Wei
    fee: Wei
    distribution_hint: list[OutcomeWei] | None

    @property
    def url(self) -> str:
        return construct_presagio_url(
            self.market_event.fixed_product_market_maker_checksummed
        )


class ContractPrediction(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    market: str | None = Field(
        None,
        alias="marketAddress",
        description="Market's address. Will be None on older records.",
    )
    publisher: str = Field(..., alias="publisherAddress")
    ipfs_hash: HexBytes = Field(..., alias="ipfsHash")
    tx_hashes: list[HexBytes] = Field(..., alias="txHashes")
    outcomes: list[OutcomeStr] = Field(...)
    estimated_probabilities_bps: list[int] = Field(
        ..., alias="estimatedProbabilitiesBps"
    )

    @model_validator(mode="before")
    @classmethod
    def handle_legacy_estimated_probability_bps(
        cls, values: dict[str, t.Any]
    ) -> dict[str, t.Any]:
        # If 'estimatedProbabilityBps' is present and 'outcomes'/'estimatedProbabilitiesBps' are not,
        # convert to the new format using "Yes" and "No" outcomes.
        # This allows for backward compatibility with old contract events.
        if (
            "estimatedProbabilityBps" in values
            and "outcomes" not in values
            and "estimatedProbabilitiesBps" not in values
        ):
            prob_bps = values["estimatedProbabilityBps"]
            values["outcomes"] = [
                OMEN_TRUE_OUTCOME,
                OMEN_FALSE_OUTCOME,
            ]
            values["estimatedProbabilitiesBps"] = [prob_bps, BPS_CONSTANT - prob_bps]
        return values

    def estimated_probability_of_outcome(self, outcome: OutcomeStr) -> Probability:
        index = self.outcomes.index(outcome)
        return Probability(self.estimated_probabilities_bps[index] / BPS_CONSTANT)

    @computed_field  # type: ignore[prop-decorator] # Mypy issue: https://github.com/python/mypy/issues/14461
    @property
    def publisher_checksummed(self) -> ChecksumAddress:
        return Web3.to_checksum_address(self.publisher)

    @staticmethod
    def from_tuple(values: tuple[t.Any, ...]) -> "ContractPrediction":
        return ContractPrediction(
            market=values[0],
            publisher=values[1],
            ipfs_hash=values[2],
            tx_hashes=values[3],
            outcomes=values[4],
            estimated_probabilities_bps=values[5],
        )


class IPFSAgentResult(BaseModel):
    reasoning: str
    agent_name: str
    model_config = ConfigDict(
        extra="forbid",
    )


class PayoutRedemptionEvent(BaseModel):
    redeemer: HexAddress
    collateralToken: HexAddress
    parentCollectionId: HexBytes
    conditionId: HexBytes
    indexSets: list[int]
    payout: Wei
