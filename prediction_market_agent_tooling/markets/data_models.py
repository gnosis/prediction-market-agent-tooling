import typing as t
from datetime import datetime
from decimal import Decimal
from enum import Enum

from pydantic import BaseModel
from web3 import Web3

from prediction_market_agent_tooling.benchmark.utils import should_not_happen
from prediction_market_agent_tooling.gtypes import (
    USD,
    ChecksumAddress,
    HexAddress,
    Mana,
    OmenOutcomeToken,
    Probability,
    Wei,
    xDai,
)


class Currency(str, Enum):
    xDai = "xDai"
    Mana = "Mana"


class Resolution(str, Enum):
    YES = "YES"
    NO = "NO"
    CANCEL = "CANCEL"


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


class AgentMarket(BaseModel):
    """
    Common market class that can be created from vendor specific markets.
    Contains everything that is needed for an agent to make a prediction.
    """

    id: str
    question: str
    outcomes: list[str]
    bet_amount_currency: Currency
    original_market: t.Union["OmenMarket", "ManifoldMarket"]


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

    def get_outcome_index(self, outcome: str) -> int:
        try:
            return self.outcomes.index(outcome)
        except ValueError:
            raise ValueError(f"Outcome `{outcome}` not found in `{self.outcomes}`.")

    def get_outcome_str(self, outcome_index: int) -> str:
        n_outcomes = len(self.outcomes)
        if outcome_index >= n_outcomes:
            raise ValueError(
                f"Outcome index `{outcome_index}` not valid. There are only "
                f"`{n_outcomes}` outcomes."
            )
        else:
            return self.outcomes[outcome_index]

    def to_agent_market(self) -> AgentMarket:
        return AgentMarket(
            id=self.id,
            question=self.title,
            outcomes=self.outcomes,
            bet_amount_currency=self.BET_AMOUNT_CURRENCY,
            original_market=self,
        )

    def __repr__(self) -> str:
        return f"Omen's market: {self.title}"


class ManifoldPool(BaseModel):
    NO: float
    YES: float


class ManifoldMarket(BaseModel):
    """
    https://docs.manifold.markets/api#get-v0markets
    """

    BET_AMOUNT_CURRENCY: Currency = Currency.Mana

    id: str
    question: str
    creatorId: str
    closeTime: datetime
    createdTime: datetime
    creatorAvatarUrl: str
    creatorName: str
    creatorUsername: str
    isResolved: bool
    resolution: t.Optional[str] = None
    resolutionTime: t.Optional[datetime] = None
    lastBetTime: t.Optional[datetime] = None
    lastCommentTime: t.Optional[datetime] = None
    lastUpdatedTime: datetime
    mechanism: str
    outcomeType: str
    p: float
    pool: ManifoldPool
    probability: Probability
    slug: str
    totalLiquidity: Mana
    uniqueBettorCount: int
    url: str
    volume: Mana
    volume24Hours: Mana

    @property
    def outcomes(self) -> list[str]:
        return list(self.pool.model_fields.keys())

    def to_agent_market(self) -> "AgentMarket":
        return AgentMarket(
            id=self.id,
            question=self.question,
            outcomes=self.outcomes,
            bet_amount_currency=self.BET_AMOUNT_CURRENCY,
            original_market=self,
        )

    def get_resolution_enum(self) -> Resolution:
        return Resolution(self.resolution)

    def is_resolved_non_cancelled(self) -> bool:
        return (
            self.isResolved
            and self.resolutionTime is not None
            and self.get_resolution_enum() != Resolution.CANCEL
        )

    def __repr__(self) -> str:
        return f"Manifold's market: {self.question}"


class ProfitCached(BaseModel):
    daily: Mana
    weekly: Mana
    monthly: Mana
    allTime: Mana


class ManifoldUser(BaseModel):
    """
    https://docs.manifold.markets/api#get-v0userusername
    """

    id: str
    createdTime: datetime
    name: str
    username: str
    url: str
    avatarUrl: t.Optional[str] = None
    bio: t.Optional[str] = None
    bannerUrl: t.Optional[str] = None
    website: t.Optional[str] = None
    twitterHandle: t.Optional[str] = None
    discordHandle: t.Optional[str] = None
    isBot: t.Optional[bool] = None
    isAdmin: t.Optional[bool] = None
    isTrustworthy: t.Optional[bool] = None
    isBannedFromPosting: t.Optional[bool] = None
    userDeleted: t.Optional[bool] = None
    balance: Mana
    totalDeposits: Mana
    lastBetTime: t.Optional[datetime] = None
    currentBettingStreak: t.Optional[int] = None
    profitCached: ProfitCached


class ManifoldBetFills(BaseModel):
    amount: Mana
    matchedBetId: t.Optional[str]
    shares: Decimal
    timestamp: int


class ManifoldBetFees(BaseModel):
    platformFee: Decimal
    liquidityFee: Decimal
    creatorFee: Decimal

    def get_total(self) -> Decimal:
        return Decimal(sum([self.platformFee, self.liquidityFee, self.creatorFee]))


class ManifoldBet(BaseModel):
    """
    https://docs.manifold.markets/api#get-v0bets
    """

    shares: Decimal
    probBefore: Probability
    isFilled: t.Optional[bool] = None
    probAfter: Probability
    userId: str
    amount: Mana
    contractId: str
    id: str
    fees: ManifoldBetFees
    isCancelled: t.Optional[bool] = None
    loanAmount: Mana
    orderAmount: t.Optional[Mana] = None
    fills: t.Optional[list[ManifoldBetFills]] = None
    createdTime: datetime
    outcome: str

    def get_resolved_boolean_outcome(self) -> bool:
        outcome = Resolution(self.outcome)
        if outcome == Resolution.YES:
            return True
        elif outcome == Resolution.NO:
            return False
        else:
            should_not_happen(f"Unexpected bet outcome string, '{outcome.value}'.")

    def get_profit(self, market_outcome: bool) -> ProfitAmount:
        profit = (
            self.shares - self.amount
            if self.get_resolved_boolean_outcome() == market_outcome
            else -self.amount
        )
        profit -= self.fees.get_total()
        return ProfitAmount(
            amount=profit,
            currency=Currency.Mana,
        )


class ManifoldContractMetric(BaseModel):
    """
    https://docs.manifold.markets/api#get-v0marketmarketidpositions
    """

    contractId: str
    hasNoShares: bool
    hasShares: bool
    hasYesShares: bool
    invested: Decimal
    loan: Decimal
    maxSharesOutcome: t.Optional[str]
    payout: Decimal
    profit: Decimal
    profitPercent: Decimal
    totalShares: dict[str, Decimal]
    userId: str
    userUsername: str
    userName: str
    userAvatarUrl: str
    lastBetTime: datetime
