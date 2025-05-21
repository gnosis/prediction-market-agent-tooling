import time

import pytest

from prediction_market_agent_tooling.config import APIKeys
from prediction_market_agent_tooling.markets.agent_market import FilterBy, SortBy
from prediction_market_agent_tooling.markets.omen.data_models import OMEN_TRUE_OUTCOME
from prediction_market_agent_tooling.markets.omen.omen import OmenAgentMarket
from prediction_market_agent_tooling.tools.utils import utcnow
from tests.utils import RUN_PAID_TESTS


@pytest.mark.skipif(not RUN_PAID_TESTS, reason="This test costs money to run.")
def test_match_bet_ids_with_get_subgraph_bets() -> None:
    market = OmenAgentMarket.get_markets(
        limit=1,
        sort_by=SortBy.CLOSING_SOONEST,
        filter_by=FilterBy.OPEN,
    )[0]
    now = utcnow()
    id0 = market.buy_tokens(
        outcome=OMEN_TRUE_OUTCOME,
        amount=market.get_token_in_usd(market.get_tiny_bet_amount()),
    )
    id1 = market.buy_tokens(
        outcome=OMEN_TRUE_OUTCOME,
        amount=market.get_token_in_usd(market.get_tiny_bet_amount()),
    )
    assert id0 != id1

    time.sleep(10)  # wait for the subgraph to index the bets
    keys = APIKeys()
    bets = OmenAgentMarket.get_bets_made_since(
        better_address=keys.bet_from_address,
        start_time=now,
    )
    # Ensure bets are sorted by ascending time
    bets = sorted(bets, key=lambda bet: bet.created_time)
    assert len(bets) == 2
    assert bets[0].id == id0
    assert bets[1].id == id1
