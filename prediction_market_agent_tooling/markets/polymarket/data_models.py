import json
from enum import Enum

from pydantic import BaseModel

from prediction_market_agent_tooling.gtypes import (
    USD,
    USDC,
    CollateralToken,
    OutcomeStr,
    OutcomeToken,
    Probability,
    VerifiedChecksumAddress,
)
from prediction_market_agent_tooling.markets.data_models import (
    Bet,
    Resolution,
    ResolvedBet,
)
from prediction_market_agent_tooling.markets.polymarket.constants import (
    POLYMARKET_BASE_URL,
)
from prediction_market_agent_tooling.tools.hexbytes_custom import HexBytes
from prediction_market_agent_tooling.tools.utils import DatetimeUTC

POLYMARKET_TRUE_OUTCOME = "Yes"
POLYMARKET_FALSE_OUTCOME = "No"


class PolymarketSideEnum(str, Enum):
    BUY = "BUY"
    SELL = "SELL"


# TODO: Use when CLOB API is introduced for real-time trading.
class PolymarketRewards(BaseModel):
    min_size: int
    max_spread: float | None
    event_start_date: DatetimeUTC | None = None
    event_end_date: DatetimeUTC | None = None
    in_game_multiplier: int | None = None
    reward_epoch: int | None = None


class PolymarketToken(BaseModel):
    token_id: str
    outcome: OutcomeStr
    winner: bool


class PolymarketGammaMarket(BaseModel):
    conditionId: HexBytes
    outcomes: str
    outcomePrices: str | None = None
    marketMakerAddress: str
    createdAt: DatetimeUTC
    updatedAt: DatetimeUTC | None = None
    archived: bool
    questionId: str | None = None
    clobTokenIds: str | None = None  # int-encoded hex
    question: str | None = None
    negRisk: bool | None = None
    negRiskMarketID: str | None = None
    negRiskFeeBips: int | None = None
    acceptingOrders: bool | None = None
    enableOrderBook: bool | None = None
    makerBaseFee: int | None = None
    takerBaseFee: int | None = None
    fee: str | None = None

    @property
    def token_ids(self) -> list[int]:
        if not self.clobTokenIds:
            raise ValueError("Market has no token_ids")
        try:
            return [int(i) for i in json.loads(self.clobTokenIds)]
        except (json.JSONDecodeError, ValueError, TypeError) as e:
            raise ValueError(
                f"Invalid clobTokenIds JSON '{self.clobTokenIds}': {e}"
            ) from e

    @property
    def outcomes_list(self) -> list[OutcomeStr]:
        try:
            return [OutcomeStr(i) for i in json.loads(self.outcomes)]
        except (json.JSONDecodeError, TypeError) as e:
            raise ValueError(f"Invalid outcomes JSON '{self.outcomes}': {e}") from e

    @property
    def outcome_prices(self) -> list[float] | None:
        if not self.outcomePrices:
            return None
        try:
            return [float(i) for i in json.loads(self.outcomePrices)]
        except (json.JSONDecodeError, ValueError, TypeError) as e:
            raise ValueError(
                f"Invalid outcomePrices JSON '{self.outcomePrices}': {e}"
            ) from e


class PolymarketGammaTag(BaseModel):
    label: str
    slug: str


class PolymarketGammaResponseDataItem(BaseModel):
    id: str
    slug: str
    volume: float | None = None
    startDate: DatetimeUTC | None = None
    endDate: DatetimeUTC | None = None
    liquidity: float | None = None
    liquidityClob: float | None = None
    title: str
    description: str | None = None
    archived: bool
    closed: bool
    active: bool
    markets: list[PolymarketGammaMarket] | None = (
        None  # Some Polymarket markets have missing markets field. We skip these markets manually when retrieving.
    )
    negRisk: bool | None = None
    negRiskMarketID: str | None = None
    negRiskFeeBips: int | None = None
    enableNegRisk: bool | None = None
    tags: list[PolymarketGammaTag] = []

    @property
    def url(self) -> str:
        return construct_polymarket_url(self.slug)


class PolymarketGammaPagination(BaseModel):
    hasMore: bool


class PolymarketGammaResponse(BaseModel):
    data: list[PolymarketGammaResponseDataItem]
    pagination: PolymarketGammaPagination


# TODO: Use when CLOB API is introduced for real-time trading.
class PolymarketMarket(BaseModel):
    enable_order_book: bool
    active: bool
    closed: bool
    archived: bool
    minimum_order_size: str | float
    minimum_tick_size: str | float
    condition_id: str
    question_id: str
    question: str
    description: str
    market_slug: str
    end_date_iso: DatetimeUTC | None
    game_start_time: DatetimeUTC | None
    seconds_delay: int
    fpmm: str
    maker_base_fee: int
    taker_base_fee: int
    notifications_enabled: bool
    neg_risk: bool
    neg_risk_market_id: str
    neg_risk_request_id: str
    icon: str
    image: str
    rewards: PolymarketRewards
    tokens: tuple[PolymarketToken, ...]
    is_50_50_outcome: bool
    categories: list[str] | None = None
    parent_categories: list[str] | None = None
    accepting_orders: bool

    @property
    def id(self) -> str:
        return self.condition_id

    @property
    def url(self) -> str:
        return construct_polymarket_url(self.market_slug)

    @property
    def resolution(self) -> Resolution | None:
        winner_tokens = [token for token in self.tokens if token.winner]
        if len(winner_tokens) == 0:
            return Resolution(outcome=None, invalid=True)
        elif (
            len(winner_tokens) == 1
            and winner_tokens[0].outcome == POLYMARKET_TRUE_OUTCOME
        ):
            return Resolution(
                outcome=OutcomeStr(POLYMARKET_TRUE_OUTCOME), invalid=False
            )
        elif (
            len(winner_tokens) == 1
            and winner_tokens[0].outcome == POLYMARKET_FALSE_OUTCOME
        ):
            return Resolution(
                outcome=OutcomeStr(POLYMARKET_FALSE_OUTCOME), invalid=False
            )
        else:
            raise ValueError(
                f"Should not happen, invalid winner tokens: {winner_tokens}"
            )


# TODO: Use when CLOB API is introduced for real-time trading.
class MarketsEndpointResponse(BaseModel):
    limit: int
    count: int
    next_cursor: str
    data: list[PolymarketMarket]


# TODO: Use when CLOB API is introduced for real-time trading.
class PolymarketPriceResponse(BaseModel):
    price: str

    @property
    def price_dec(self) -> USDC:
        return USDC(self.price)


class Prices(BaseModel):
    BUY: USDC
    SELL: USDC


class PolymarketTokenWithPrices(PolymarketToken):
    prices: Prices


class PolymarketMarketWithPrices(PolymarketMarket):
    tokens: tuple[PolymarketTokenWithPrices, ...]

    @property
    def p_yes(self) -> Probability:
        for token in self.tokens:
            if token.outcome == POLYMARKET_TRUE_OUTCOME:
                return Probability(float(token.prices.BUY))
        raise ValueError(
            "Should not happen, as we filter only for binary markets in get_polymarket_binary_markets."
        )


class PolymarketPositionResponse(BaseModel):
    slug: str
    eventSlug: str
    proxyWallet: str
    asset: str
    conditionId: str
    size: float
    currentValue: float
    cashPnl: float
    redeemable: bool
    outcome: str
    outcomeIndex: int

    @property
    def size_as_outcome_token(self) -> OutcomeToken:
        return OutcomeToken(self.size)

    @property
    def current_value_usd(self) -> USD:
        return USD(self.currentValue)

    @property
    def cash_pnl_usd(self) -> USD:
        return USD(self.cashPnl)


class PolymarketBet(BaseModel):
    id: str
    taker_order_id: str
    market: HexBytes
    asset_id: str  # token_id (large integer)
    side: PolymarketSideEnum
    size: float  # number of outcome tokens
    fee_rate_bps: int
    price: float  # execution price (0-1)
    status: str
    match_time: DatetimeUTC
    outcome: OutcomeStr
    event_slug: str
    title: str

    @property
    def cost(self) -> CollateralToken:
        return CollateralToken(self.size * self.price)

    def get_profit(self, resolution: Resolution) -> CollateralToken:
        if resolution.invalid or resolution.outcome is None:
            return CollateralToken(0)

        is_winning = self.outcome == resolution.outcome

        if self.side == PolymarketSideEnum.BUY:
            if is_winning:
                return CollateralToken(self.size * (1 - self.price))
            else:
                return CollateralToken(-self.size * self.price)
        else:  # SELL
            if is_winning:
                return CollateralToken(-self.size * (1 - self.price))
            else:
                return CollateralToken(self.size * self.price)

    def to_bet(self) -> Bet:
        return Bet(
            id=self.id,
            amount=self.cost,
            outcome=self.outcome,
            created_time=self.match_time,
            market_question=self.title,
            market_id=self.market.to_0x_hex(),
        )

    def to_generic_resolved_bet(
        self, resolution: Resolution, resolved_time: DatetimeUTC
    ) -> ResolvedBet:
        if resolution.invalid or resolution.outcome is None:
            raise ValueError(
                f"Trade {self.id} cannot be converted to a resolved bet: "
                f"resolution is invalid or has no outcome."
            )

        return ResolvedBet(
            id=self.id,
            amount=self.cost,
            outcome=self.outcome,
            created_time=self.match_time,
            market_question=self.title,
            market_id=self.market.to_0x_hex(),
            market_outcome=resolution.outcome,
            resolved_time=resolved_time,
            profit=self.get_profit(resolution),
        )


class PolymarketTradeResponse(BaseModel):
    proxyWallet: VerifiedChecksumAddress
    side: PolymarketSideEnum
    asset: str  # token_id (large integer)
    conditionId: HexBytes
    size: float  # outcome tokens (can be fractional)
    price: float  # execution price (0-1)
    timestamp: DatetimeUTC
    title: str
    slug: str
    icon: str
    eventSlug: str
    outcome: OutcomeStr
    outcomeIndex: int
    name: str
    pseudonym: str
    bio: str
    profileImage: str
    profileImageOptimized: str
    transactionHash: HexBytes

    @property
    def cost(self) -> CollateralToken:
        return CollateralToken(self.size * self.price)

    def to_polymarket_bet(self) -> PolymarketBet:
        """Convert Data API trade to PolymarketBet for profit/bet logic reuse."""
        return PolymarketBet(
            id=self.transactionHash.to_0x_hex(),
            taker_order_id="",
            market=self.conditionId,
            asset_id=self.asset,
            side=self.side,
            size=self.size,
            fee_rate_bps=0,
            price=self.price,
            status="MATCHED",
            match_time=self.timestamp,
            outcome=self.outcome,
            event_slug=self.eventSlug,
            title=self.title,
        )


def construct_polymarket_url(slug: str) -> str:
    """
    Note: This works only if it's a single main market, not sub-market of some more general question.
    """
    return f"{POLYMARKET_BASE_URL}/event/{slug}"
