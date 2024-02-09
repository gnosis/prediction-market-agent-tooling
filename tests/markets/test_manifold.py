import pytest
from tests.utils import RUN_PAID_TESTS
from prediction_market_agent_tooling.config import APIKeys
from prediction_market_agent_tooling.markets import manifold
from prediction_market_agent_tooling.gtypes import mana_type


@pytest.mark.skipif(not RUN_PAID_TESTS, reason="This test costs money to run.")
def test_manifold() -> None:
    market = manifold.pick_binary_market()
    print("Placing bet on market:", market.question)
    manifold.place_bet(mana_type(0.01), market.id, True, APIKeys().manifold_api_key)
