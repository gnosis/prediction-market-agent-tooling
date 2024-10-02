from pydantic import BaseModel

from prediction_market_agent_tooling.gtypes import USDC, Probability, usdc_type
from prediction_market_agent_tooling.markets.data_models import Resolution
from prediction_market_agent_tooling.markets.polymarket.data_models_web import (
    POLYMARKET_FALSE_OUTCOME,
    POLYMARKET_TRUE_OUTCOME,
    PolymarketFullMarket,
    construct_polymarket_url,
)
from prediction_market_agent_tooling.tools.utils import DatetimeUTCValidator


class PolymarketRewards(BaseModel):
    min_size: int
    max_spread: float | None
    event_start_date: DatetimeUTCValidator | None = None
    event_end_date: DatetimeUTCValidator | None = None
    in_game_multiplier: int | None = None
    reward_epoch: int | None = None


class PolymarketToken(BaseModel):
    token_id: str
    outcome: str
    winner: bool


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
    end_date_iso: DatetimeUTCValidator | None
    game_start_time: DatetimeUTCValidator | None
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
            return None
        elif (
            len(winner_tokens) == 1
            and winner_tokens[0].outcome == POLYMARKET_TRUE_OUTCOME
        ):
            return Resolution.YES
        elif (
            len(winner_tokens) == 1
            and winner_tokens[0].outcome == POLYMARKET_FALSE_OUTCOME
        ):
            return Resolution.NO
        else:
            raise ValueError(
                f"Should not happen, invalid winner tokens: {winner_tokens}"
            )

    def fetch_full_market(self) -> PolymarketFullMarket | None:
        return PolymarketFullMarket.fetch_from_url(self.url)

    def fetch_if_its_a_main_market(self) -> bool:
        # On Polymarket, there are markets that are actually a group of multiple Yes/No markets, for example https://polymarket.com/event/presidential-election-winner-2024.
        # But API returns them individually, and then we receive questions such as "Will any other Republican Politician win the 2024 US Presidential Election?",
        # which are naturally unpredictable without futher details.
        # This is a heuristic to filter them out.
        # Warning: This is a very slow operation, as it requires fetching the website. Use it only when necessary.
        full_market = self.fetch_full_market()
        # `full_market` can be None, if this class come from a multiple Yes/No market, becase then, the constructed URL is invalid (and there is now way to construct an valid one from the data we have).
        return full_market is not None and full_market.is_main_market


class MarketsEndpointResponse(BaseModel):
    limit: int
    count: int
    next_cursor: str
    data: list[PolymarketMarket]


class PolymarketPriceResponse(BaseModel):
    price: str

    @property
    def price_dec(self) -> USDC:
        return usdc_type(self.price)


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
