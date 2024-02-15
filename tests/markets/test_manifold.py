import pytest

from prediction_market_agent_tooling.gtypes import mana_type
from prediction_market_agent_tooling.markets import manifold
from tests.utils import RUN_PAID_TESTS


@pytest.mark.skipif(not RUN_PAID_TESTS, reason="This test costs money to run.")
def test_manifold() -> None:
    market = manifold.pick_binary_market()
    print("Placing bet on market:", market.question)
    manifold.place_bet(mana_type(0.01), market.id, True)
