import typing as t
from enum import Enum

from pydantic import BaseModel

from prediction_market_agent_tooling.gtypes import (
    USD,
    Mana,
    OutcomeStr,
    OutcomeToken,
    Probability,
    Token,
)
from prediction_market_agent_tooling.markets.data_models import Resolution
from prediction_market_agent_tooling.tools.utils import DatetimeUTC, should_not_happen

MANIFOLD_BASE_URL = "https://manifold.markets"


def mana_to_usd(mana: Mana) -> USD:
    # Not really, but for sake of simplicity. Mana are just play money.
    return USD(mana.value)


def usd_to_mana(usd: USD) -> Mana:
    # Not really, but for sake of simplicity. Mana are just play money.
    return Mana(usd.value)


class ManifoldPool(BaseModel):
    NO: OutcomeToken
    YES: OutcomeToken

    def size_for_outcome(self, outcome: str) -> OutcomeToken:
        if hasattr(self, outcome):
            return OutcomeToken(getattr(self, outcome))
        else:
            should_not_happen(f"Unexpected outcome string, '{outcome}'.")


class ManifoldAnswersMode(str, Enum):
    ANYONE = "ANYONE"
    ONLY_CREATOR = "ONLY_CREATOR"
    DISABLED = "DISABLED"


class ManifoldAnswer(BaseModel):
    createdTime: DatetimeUTC
    avatarUrl: str
    id: str
    username: str
    number: int
    name: str
    contractId: str
    text: str
    userId: str
    probability: float


class ManifoldMarket(BaseModel):
    """
    https://docs.manifold.markets/api#get-v0markets
    """

    id: str
    question: str
    creatorId: str
    closeTime: DatetimeUTC
    createdTime: DatetimeUTC
    creatorAvatarUrl: t.Optional[str] = None
    creatorName: str
    creatorUsername: str
    isResolved: bool
    resolution: t.Optional[Resolution] = None
    resolutionTime: t.Optional[DatetimeUTC] = None
    lastBetTime: t.Optional[DatetimeUTC] = None
    lastCommentTime: t.Optional[DatetimeUTC] = None
    lastUpdatedTime: DatetimeUTC
    mechanism: str
    outcomeType: str
    p: t.Optional[float] = None
    pool: ManifoldPool
    probability: Probability
    slug: str
    totalLiquidity: t.Optional[Token] = None
    uniqueBettorCount: int
    url: str
    volume: Token
    volume24Hours: Token

    @property
    def outcomes(self) -> t.Sequence[OutcomeStr]:
        return [OutcomeStr(o) for o in self.pool.model_fields.keys()]

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


class FullManifoldMarket(ManifoldMarket):
    # Some of these fields are available only in specific cases, see https://docs.manifold.markets/api#get-v0marketmarketid.
    answers: list[ManifoldAnswer] | None = None
    shouldAnswersSumToOne: bool | None = None
    addAnswersMode: ManifoldAnswersMode | None = None
    options: dict[str, int | str] | None = None
    totalBounty: float | None = None
    bountyLeft: float | None = None
    description: str | dict[str, t.Any]
    textDescription: str
    coverImageUrl: str | None = None
    groupSlugs: list[str] | None = None


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
    createdTime: DatetimeUTC
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
    lastBetTime: t.Optional[DatetimeUTC] = None
    currentBettingStreak: t.Optional[int] = None
    profitCached: ProfitCached


class ManifoldBetFills(BaseModel):
    amount: Mana
    matchedBetId: t.Optional[str]
    shares: float
    timestamp: int


class ManifoldBetFees(BaseModel):
    platformFee: float
    liquidityFee: float
    creatorFee: float

    def get_total(self) -> float:
        return sum([self.platformFee, self.liquidityFee, self.creatorFee])


class ManifoldBet(BaseModel):
    """
    https://docs.manifold.markets/api#get-v0bets
    """

    shares: Token
    probBefore: Probability
    isFilled: t.Optional[bool] = None
    probAfter: Probability
    userId: str
    amount: Token
    contractId: str
    id: str
    fees: ManifoldBetFees
    isCancelled: t.Optional[bool] = None
    loanAmount: Token | None
    orderAmount: t.Optional[Token] = None
    fills: t.Optional[list[ManifoldBetFills]] = None
    createdTime: DatetimeUTC
    outcome: Resolution

    def get_resolved_boolean_outcome(self) -> bool:
        if self.outcome == Resolution.YES:
            return True
        elif self.outcome == Resolution.NO:
            return False
        else:
            should_not_happen(f"Unexpected bet outcome string, '{self.outcome.value}'.")

    def get_profit(self, market_outcome: bool) -> Token:
        profit = (
            self.shares - self.amount
            if self.get_resolved_boolean_outcome() == market_outcome
            else -self.amount
        )
        return profit


class ManifoldContractMetric(BaseModel):
    """
    https://docs.manifold.markets/api#get-v0marketmarketidpositions
    """

    contractId: str
    hasNoShares: bool
    hasShares: bool
    hasYesShares: bool
    invested: float
    loan: float
    maxSharesOutcome: t.Optional[str]
    payout: float
    profit: float
    profitPercent: float
    totalShares: dict[str, float]
    userId: str
    userUsername: str
    userName: str
    userAvatarUrl: str
    lastBetTime: DatetimeUTC
