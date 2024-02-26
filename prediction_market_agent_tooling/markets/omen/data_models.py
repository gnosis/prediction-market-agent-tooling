import typing as t
from datetime import datetime
from decimal import Decimal

from eth_typing import ChecksumAddress, HexAddress
from pydantic import BaseModel
from web3 import Web3

from prediction_market_agent_tooling.gtypes import (
    USD,
    OmenOutcomeToken,
    Probability,
    Wei,
    xDai,
)
from prediction_market_agent_tooling.markets.data_models import (
    BetAmount,
    Currency,
    ProfitAmount,
    ResolvedBet,
)
from prediction_market_agent_tooling.tools.utils import check_not_none
from prediction_market_agent_tooling.tools.web3_utils import wei_to_xdai

OMEN_TRUE_OUTCOME = "Yes"
OMEN_FALSE_OUTCOME = "No"


def get_boolean_outcome(outcome_str: str) -> bool:
    if outcome_str == OMEN_TRUE_OUTCOME:
        return True
    if outcome_str == OMEN_FALSE_OUTCOME:
        return False
    raise ValueError(f"Outcome `{outcome_str}` is not a valid boolean outcome.")


class OmenMarket(BaseModel):
    """
    https://aiomen.eth.limo
    """

    BET_AMOUNT_CURRENCY: t.ClassVar[Currency] = Currency.xDai

    id: HexAddress
    title: str
    collateralVolume: Wei
    usdVolume: USD
    collateralToken: HexAddress
    outcomes: list[str]
    outcomeTokenAmounts: list[OmenOutcomeToken]
    outcomeTokenMarginalPrices: t.Optional[list[xDai]]
    fee: t.Optional[Wei]

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
    def p_yes(self) -> Probability:
        return check_not_none(
            self.outcomeTokenProbabilities,
            "outcomeTokenProbabilities not available",
        )[self.outcomes.index(OMEN_TRUE_OUTCOME)]

    @property
    def p_no(self) -> Probability:
        return Probability(1 - self.p_yes)

    def __repr__(self) -> str:
        return f"Omen's market: {self.title}"


class OmenBetCreator(BaseModel):
    id: HexAddress


class OmenBetFPMM(BaseModel):
    id: HexAddress
    outcomes: list[str]
    title: str
    answerFinalizedTimestamp: t.Optional[int] = None
    currentAnswer: t.Optional[str] = None
    isPendingArbitration: bool
    arbitrationOccurred: bool
    openingTimestamp: int

    @property
    def is_resolved(self) -> bool:
        return (
            self.answerFinalizedTimestamp is not None and self.currentAnswer is not None
        )

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

        return get_boolean_outcome(check_not_none(self.currentAnswer))


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
    fpmm: OmenBetFPMM

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
                f"Bet with title {self.title} is not resolved. It has no resolved time."
            )

        return ResolvedBet(
            amount=BetAmount(
                amount=Decimal(self.collateralAmountUSD), currency=Currency.xDai
            ),
            outcome=self.boolean_outcome,
            created_time=datetime.fromtimestamp(self.creationTimestamp),
            market_question=self.title,
            market_outcome=self.fpmm.boolean_outcome,
            resolved_time=datetime.fromtimestamp(self.fpmm.answerFinalizedTimestamp),  # type: ignore # TODO Mypy doesn't understand that self.fpmm.is_resolved is True and therefore timestamp is known non-None
            profit=self.get_profit(),
        )
