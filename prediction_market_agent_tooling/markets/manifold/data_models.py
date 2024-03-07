import typing as t
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel

from prediction_market_agent_tooling.benchmark.utils import should_not_happen
from prediction_market_agent_tooling.gtypes import Mana, Probability
from prediction_market_agent_tooling.markets.data_models import (
    Currency,
    ProfitAmount,
    Resolution,
)


class ManifoldPool(BaseModel):
    NO: float
    YES: float


class ManifoldMarket(BaseModel):
    """
    https://docs.manifold.markets/api#get-v0markets
    """

    BET_AMOUNT_CURRENCY: t.ClassVar[Currency] = Currency.Mana

    id: str
    question: str
    creatorId: str
    closeTime: datetime
    createdTime: datetime
    creatorAvatarUrl: t.Optional[str] = None
    creatorName: str
    creatorUsername: str
    isResolved: bool
    resolution: t.Optional[Resolution] = None
    resolutionTime: t.Optional[datetime] = None
    lastBetTime: t.Optional[datetime] = None
    lastCommentTime: t.Optional[datetime] = None
    lastUpdatedTime: datetime
    mechanism: str
    outcomeType: str
    p: t.Optional[float] = None
    pool: ManifoldPool
    probability: Probability
    slug: str
    totalLiquidity: t.Optional[Mana] = None
    uniqueBettorCount: int
    url: str
    volume: Mana
    volume24Hours: Mana

    @property
    def outcomes(self) -> list[str]:
        return list(self.pool.model_fields.keys())

    def get_resolved_boolean_outcome(self) -> bool:
        if self.resolution == Resolution.YES:
            return True
        elif self.resolution == Resolution.NO:
            return False
        else:
            should_not_happen(f"Unexpected bet outcome string, '{self.resolution}'.")

    def is_resolved_non_cancelled(self) -> bool:
        return (
            self.isResolved
            and self.resolutionTime is not None
            and self.resolution not in [Resolution.CANCEL, Resolution.MKT]
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
    outcome: Resolution

    def get_resolved_boolean_outcome(self) -> bool:
        if self.outcome == Resolution.YES:
            return True
        elif self.outcome == Resolution.NO:
            return False
        else:
            should_not_happen(f"Unexpected bet outcome string, '{self.outcome.value}'.")

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
