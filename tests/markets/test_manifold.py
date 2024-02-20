import pytest

from prediction_market_agent_tooling.gtypes import mana_type
from prediction_market_agent_tooling.markets.manifold.api import (
    pick_binary_market,
    place_bet,
)
from tests.utils import RUN_PAID_TESTS


@pytest.mark.skipif(not RUN_PAID_TESTS, reason="This test costs money to run.")
def test_manifold() -> None:
    market = pick_binary_market()
    print("Placing bet on market:", market.question)
    place_bet(mana_type(0.01), market.id, True)
