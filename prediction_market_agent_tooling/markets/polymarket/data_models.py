import json

from pydantic import BaseModel

from prediction_market_agent_tooling.gtypes import USDC, OutcomeStr, Probability
from prediction_market_agent_tooling.markets.data_models import Resolution
from prediction_market_agent_tooling.markets.polymarket.data_models_web import (
    POLYMARKET_FALSE_OUTCOME,
    POLYMARKET_TRUE_OUTCOME,
    construct_polymarket_url,
)
from prediction_market_agent_tooling.tools.hexbytes_custom import HexBytes
from prediction_market_agent_tooling.tools.utils import DatetimeUTC


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

    @property
    def outcomes_list(self) -> list[OutcomeStr]:
        return [OutcomeStr(i) for i in json.loads(self.outcomes)]

    @property
    def outcome_prices(self) -> list[float] | None:
        if not self.outcomePrices:
            return None
        return [float(i) for i in json.loads(self.outcomePrices)]


class PolymarketGammaTag(BaseModel):
    label: str
    slug: str


class PolymarketGammaResponseDataItem(BaseModel):
    id: str
    slug: str
    volume: float | None = None
    startDate: DatetimeUTC
    endDate: DatetimeUTC | None = None
    liquidity: float | None = None
    liquidityClob: float | None = None
    title: str
    description: str
    archived: bool
    closed: bool
    active: bool
    markets: list[PolymarketGammaMarket]
    tags: list[PolymarketGammaTag]

    @property
    def url(self) -> str:
        return construct_polymarket_url(self.slug)


class PolymarketGammaPagination(BaseModel):
    hasMore: bool


class PolymarketGammaResponse(BaseModel):
    data: list[PolymarketGammaResponseDataItem]
    pagination: PolymarketGammaPagination


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


class MarketsEndpointResponse(BaseModel):
    limit: int
    count: int
    next_cursor: str
    data: list[PolymarketMarket]


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
