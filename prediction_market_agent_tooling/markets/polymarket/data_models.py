from datetime import datetime

import requests
from pydantic import BaseModel

from prediction_market_agent_tooling.gtypes import USDC, Probability, usdc_type
from prediction_market_agent_tooling.markets.data_models import Resolution

POLYMARKET_TRUE_OUTCOME = "Yes"
POLYMARKET_FALSE_OUTCOME = "No"


class PolymarketRewards(BaseModel):
    min_size: int
    max_spread: float
    event_start_date: datetime | None
    event_end_date: datetime | None
    in_game_multiplier: int
    reward_epoch: int


class PolymarketToken(BaseModel):
    token_id: str
    outcome: str
    winner: bool


class PolymarketMarket(BaseModel):
    enable_order_book: bool
    active: bool
    closed: bool
    archived: bool
    minimum_order_size: str
    minimum_tick_size: str
    condition_id: str
    question_id: str
    question: str
    description: str
    market_slug: str
    end_date_iso: datetime | None
    game_start_time: datetime | None
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
    categories: list[str]
    parent_categories: list[str]
    accepting_orders: bool

    @property
    def id(self) -> str:
        return self.condition_id

    @property
    def url(self) -> str:
        """
        Note: This works only if it's a single main market, not sub-market of some more general question.
        """
        return f"https://polymarket.com/event/{self.market_slug}"

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

    def check_if_its_a_single_market(self) -> bool:
        # On Polymarket, there are markets that are actually a group of multiple Yes/No markets, for example https://polymarket.com/event/presidential-election-winner-2024.
        # But API returns them individually, and then we receive questions such as "Will any other Republican Politician win the 2024 US Presidential Election?",
        # which are naturally unpredictable without futher details.
        # This is a heuristic to filter them out.
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/58.0.3029.110 Safari/537.3"
        }
        return self.question in requests.get(self.url, headers=headers).text


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
