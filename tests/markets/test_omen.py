import time
from datetime import datetime

import pytest
from web3 import Web3

from prediction_market_agent_tooling.config import APIKeys
from prediction_market_agent_tooling.gtypes import xdai_type
from prediction_market_agent_tooling.markets.omen.omen import (
    OmenAgentMarket,
    binary_omen_buy_outcome_tx,
    binary_omen_sell_outcome_tx,
    get_market,
    get_omen_bets,
    pick_binary_market,
)
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


def test_get_bets() -> None:
    AN_ADDRESS = Web3.to_checksum_address("0x3666DA333dAdD05083FEf9FF6dDEe588d26E4307")
    bets = get_omen_bets(
        better_address=AN_ADDRESS,
        start_time=datetime(2024, 2, 20),
        end_time=datetime(2024, 2, 21),
    )
    assert len(bets) == 1
    assert (
        bets[0].id
        == "0x5b1457bb7525eed03d3c78a542ce6d89be6090e10x3666da333dadd05083fef9ff6ddee588d26e43070x1"
    )
