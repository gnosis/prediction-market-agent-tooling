from datetime import timedelta

from prediction_market_agent_tooling.config import APIKeys
from prediction_market_agent_tooling.markets.agent_market import FilterBy, SortBy
from prediction_market_agent_tooling.markets.omen.data_models import OmenMarket
from prediction_market_agent_tooling.markets.omen.omen import OmenAgentMarket
from prediction_market_agent_tooling.markets.omen.omen_subgraph_handler import (
    OmenSubgraphHandler,
)
from prediction_market_agent_tooling.tools.balances import get_balances
from prediction_market_agent_tooling.tools.betting_strategies.kelly_criterion import (
    get_kelly_bet,
)
from prediction_market_agent_tooling.tools.betting_strategies.market_moving import (
    get_market_moving_bet,
)
from prediction_market_agent_tooling.tools.utils import utcnow


def has_binary_tokens(market: OmenMarket) -> bool:
    if len(market.outcomeTokenAmounts) != 2:
        return False
    for token in market.outcomeTokenAmounts:
        if token == 0:
            return False
    return True


keys = APIKeys()
balances = get_balances(keys.bet_from_address)
total_balance = float(balances.xdai + balances.wxdai)
print(f"Total balance: {total_balance:.2f}")
bets = OmenAgentMarket.get_bets_made_since(
    better_address=keys.bet_from_address, start_time=utcnow() - timedelta(days=21)
)

open_markets = OmenSubgraphHandler().get_omen_binary_markets_simple(
    limit=10,
    sort_by=SortBy.CLOSING_SOONEST,
    filter_by=FilterBy.OPEN,
)
for market in open_markets:
    market_moving_bet_95 = get_market_moving_bet(market=market, target_p_yes=0.95)[0]
    market_moving_bet_05 = get_market_moving_bet(market=market, target_p_yes=0.05)[0]
    kelly_bet_yes = get_kelly_bet(
        market_p_yes=market.current_p_yes,
        estimated_p_yes=1.0,
        confidence=1.0,
        max_bet=total_balance,
    ).size
    kelly_bet_no = get_kelly_bet(
        market_p_yes=market.current_p_yes,
        estimated_p_yes=0.0,
        confidence=1.0,
        max_bet=total_balance,
    ).size
    print(
        f"{market.title[:20]}..., p_yes: {market.current_p_yes:.2f} mm_95: {market_moving_bet_95:.2f}, kelly_yes: {kelly_bet_yes:.2f}, mm_05: {market_moving_bet_05:.2f} kelly_no: {kelly_bet_no:.2f}"
    )


"""
## Replicator

Will Nvidia be the l..., p_yes: 0.46 mm_95: 31.38, kelly_yes: 76.80, mm_05: 31.38 kelly_no: 91.85
Will Kamala Harris g..., p_yes: 0.59 mm_95: 31.71, kelly_yes: 98.66, mm_05: 39.64 kelly_no: 69.99
Will any part of the..., p_yes: 0.57 mm_95: 31.55, kelly_yes: 95.92, mm_05: 31.55 kelly_no: 72.73
Will Trump replace J..., p_yes: 0.43 mm_95: 31.54, kelly_yes: 72.83, mm_05: 31.54 kelly_no: 95.82
Will Donald Trump be..., p_yes: 0.51 mm_95: 31.26, kelly_yes: 86.03, mm_05: 31.26 kelly_no: 82.62
Will Manifold hire a..., p_yes: 0.50 mm_95: 31.25, kelly_yes: 84.33, mm_05: 31.25 kelly_no: 84.33
Will OpenAI release ..., p_yes: 0.50 mm_95: 31.25, kelly_yes: 84.33, mm_05: 31.25 kelly_no: 84.33
Will creator of Tele..., p_yes: 0.49 mm_95: 31.26, kelly_yes: 82.29, mm_05: 31.26 kelly_no: 86.37
Will the Fed make an..., p_yes: 0.48 mm_95: 31.27, kelly_yes: 81.48, mm_05: 31.27 kelly_no: 87.17
Will Maduro lose pow..., p_yes: 0.49 mm_95: 31.26, kelly_yes: 82.29, mm_05: 31.26 kelly_no: 86.37

## Olas creator

Will the Chinese sta..., p_yes: 0.12 mm_95: 29.95, kelly_yes: 19.47, mm_05: 8.56 kelly_no: 149.18
Will the sales of LG..., p_yes: 0.51 mm_95: 21.88, kelly_yes: 85.40, mm_05: 21.88 kelly_no: 83.25
Will the Arsenal vs ..., p_yes: 0.53 mm_95: 21.92, kelly_yes: 89.60, mm_05: 21.92 kelly_no: 79.05
Will Coco Gauff win ..., p_yes: 0.14 mm_95: 31.45, kelly_yes: 23.73, mm_05: 15.73 kelly_no: 144.92
Will the average rat..., p_yes: 0.50 mm_95: 21.88, kelly_yes: 84.33, mm_05: 21.88 kelly_no: 84.33
Will Mohamed Salah s..., p_yes: 0.49 mm_95: 21.88, kelly_yes: 82.28, mm_05: 21.88 kelly_no: 86.37
Will the court case ..., p_yes: 0.50 mm_95: 21.88, kelly_yes: 84.33, mm_05: 21.88 kelly_no: 84.33
Will the content car..., p_yes: 0.73 mm_95: 18.42, kelly_yes: 122.66, mm_05: 24.56 kelly_no: 45.99
Will the California ..., p_yes: 0.57 mm_95: 22.06, kelly_yes: 95.31, mm_05: 22.06 kelly_no: 73.34
Will Liverpool forwa..., p_yes: 0.50 mm_95: 21.88, kelly_yes: 83.49, mm_05: 21.88 kelly_no: 85.16

## key

mm_95: bet size to move the market to p_yes = 0.95
mm_05: bet size to move the market to p_yes = 0.05
kelly_yes: bet size on 'yes' outcome if using KellyBettingStrategy and max_bet==KnownOutcomeAgent.balance
kelly_no: bet size on 'no' outcome if using KellyBettingStrategy and max_bet==KnownOutcomeAgent.balance
KnownOutcomeAgent.balance: 168.65
"""
