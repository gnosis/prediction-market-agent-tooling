import time

import pytest

from prediction_market_agent_tooling.config import APIKeys
from prediction_market_agent_tooling.gtypes import xdai_type
from prediction_market_agent_tooling.markets.omen.api import (
    binary_omen_buy_outcome_tx,
    binary_omen_sell_outcome_tx,
    get_market,
    pick_binary_market,
)
from prediction_market_agent_tooling.markets.omen.omen import OmenAgentMarket
from tests.utils import RUN_PAID_TESTS


def test_omen_pick_binary_market() -> None:
    market = pick_binary_market()
    assert market.outcomes == [
        "Yes",
        "No",
    ], "Omen binary market should have two outcomes, Yes and No."


def test_omen_get_market() -> None:
    market = get_market("0xa3e47bb771074b33f2e279b9801341e9e0c9c6d7")
    assert (
        market.title
        == "Will Bethesda's 'Indiana Jones and the Great Circle' be released by January 25, 2024?"
    ), "Omen market question doesn't match the expected value."


@pytest.mark.skipif(not RUN_PAID_TESTS, reason="This test costs money to run.")
def test_omen_buy_and_sell_outcome() -> None:
    # Tests both buying and selling, so we are back at the square one in the wallet (minues fees).
    market = OmenAgentMarket.from_data_model(pick_binary_market())
    amount = xdai_type(0.001)
    keys = APIKeys()
    binary_omen_buy_outcome_tx(
        amount=amount,
        from_address=keys.bet_from_address,
        from_private_key=keys.bet_from_private_key,
        market=market,
        binary_outcome=True,
        auto_deposit=True,
    )
    time.sleep(3.14)  # Wait for the transaction to be mined.
    binary_omen_sell_outcome_tx(
        amount=amount,
        from_address=keys.bet_from_address,
        from_private_key=keys.bet_from_private_key,
        market=market,
        binary_outcome=True,
        auto_withdraw=True,
    )
