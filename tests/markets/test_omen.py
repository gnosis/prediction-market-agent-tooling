import time
from datetime import datetime

import numpy as np
import pytest
from web3 import Web3

from prediction_market_agent_tooling.config import APIKeys
from prediction_market_agent_tooling.gtypes import omen_outcome_type, xdai_type
from prediction_market_agent_tooling.markets.agent_market import FilterBy, SortBy
from prediction_market_agent_tooling.markets.omen.omen import (
    OMEN_FALSE_OUTCOME,
    OMEN_TRUE_OUTCOME,
    OmenAgentMarket,
    binary_omen_buy_outcome_tx,
    binary_omen_sell_outcome_tx,
    get_market,
    get_omen_bets,
    get_omen_binary_markets,
    get_resolved_omen_bets,
    omen_create_market_tx,
    omen_fund_market_tx,
    omen_remove_fund_market_tx,
    pick_binary_market,
)
from prediction_market_agent_tooling.tools.utils import check_not_none
from prediction_market_agent_tooling.tools.web3_utils import xdai_to_wei
from tests.utils import RUN_PAID_TESTS


@pytest.fixture
def a_bet_from_address() -> str:
    return "0x3666DA333dAdD05083FEf9FF6dDEe588d26E4307"


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
    # You can double check your address at https://gnosisscan.io/ afterwards.
    market = OmenAgentMarket.from_data_model(pick_binary_market())
    buy_amount = xdai_type(0.00142)
    sell_amount = xdai_type(
        buy_amount / 2
    )  # There will be some fees, so this has to be lower.
    keys = APIKeys()
    binary_omen_buy_outcome_tx(
        amount=buy_amount,
        from_address=keys.bet_from_address,
        from_private_key=keys.bet_from_private_key,
        market=market,
        binary_outcome=True,
        auto_deposit=True,
    )
    time.sleep(10)  # Wait for the transaction to be mined.
    binary_omen_sell_outcome_tx(
        amount=sell_amount,
        from_address=keys.bet_from_address,
        from_private_key=keys.bet_from_private_key,
        market=market,
        binary_outcome=True,
        auto_withdraw=True,
    )


@pytest.mark.skipif(not RUN_PAID_TESTS, reason="This test costs money to run.")
def test_omen_create_market() -> None:
    # You can double check on https://aiomen.eth.limo/#/newest afterwards.
    keys = APIKeys()
    omen_create_market_tx(
        initial_funds=xdai_type(0.001),
        question="Will GNO hit $1000 by the end of the current year?",
        closing_time=datetime(year=datetime.utcnow().year, day=24, month=12),
        category="cryptocurrency",
        language="en",
        from_address=keys.bet_from_address,
        from_private_key=keys.bet_from_private_key,
        outcomes=[OMEN_TRUE_OUTCOME, OMEN_FALSE_OUTCOME],
        auto_deposit=True,
    )


@pytest.mark.skipif(not RUN_PAID_TESTS, reason="This test costs money to run.")
def test_omen_fund_and_remove_fund_market() -> None:
    # You can double check your address at https://gnosisscan.io/ afterwards or at the market's address.
    market = OmenAgentMarket.from_data_model(pick_binary_market())
    print(
        "Fund and remove funding market test address:",
        market.market_maker_contract_address_checksummed,
    )

    funds = xdai_type(0.1)
    remove_fund = omen_outcome_type(xdai_to_wei(xdai_type(0.01)))
    keys = APIKeys()
    omen_fund_market_tx(
        market=market,
        funds=funds,
        from_address=keys.bet_from_address,
        from_private_key=keys.bet_from_private_key,
        auto_deposit=True,
    )
    time.sleep(10)  # Wait for the transaction to be mined.
    omen_remove_fund_market_tx(
        market=market,
        shares=remove_fund,
        from_address=keys.bet_from_address,
        from_private_key=keys.bet_from_private_key,
        auto_withdraw=False,  # Switch to true after implemented.
    )


def test_get_bets(a_bet_from_address: str) -> None:
    better_address = Web3.to_checksum_address(a_bet_from_address)
    bets = get_omen_bets(
        better_address=better_address,
        start_time=datetime(2024, 2, 20),
        end_time=datetime(2024, 2, 21),
    )
    assert len(bets) == 1
    assert (
        bets[0].id
        == "0x5b1457bb7525eed03d3c78a542ce6d89be6090e10x3666da333dadd05083fef9ff6ddee588d26e43070x1"
    )


def test_p_yes() -> None:
    # Find a market with outcomeTokenMarginalPrices and verify that p_yes is correct.
    for m in get_omen_binary_markets(
        limit=200,
        sort_by=SortBy.NEWEST,
        filter_by=FilterBy.OPEN,
    ):
        if m.outcomeTokenProbabilities is not None:
            market = m
            break
    assert market is not None, "No market found with outcomeTokenProbabilities."
    assert np.isclose(market.p_yes, check_not_none(market.outcomeTokenProbabilities)[0])


def test_filter_markets() -> None:
    limit = 100
    markets = get_omen_binary_markets(
        limit=limit,
        sort_by=SortBy.NEWEST,
        filter_by=FilterBy.OPEN,
    )
    assert len(markets) == limit

    markets = get_omen_binary_markets(
        limit=limit,
        sort_by=SortBy.NEWEST,
        filter_by=FilterBy.RESOLVED,
    )
    assert len(markets) == limit


def test_resolved_omen_bets(a_bet_from_address: str) -> None:
    better_address = Web3.to_checksum_address(a_bet_from_address)
    resolved_bets = get_resolved_omen_bets(
        better_address=better_address,
        start_time=datetime(2024, 2, 20),
        end_time=datetime(2024, 2, 28),
    )

    # Verify that the bets are unique.
    assert len(resolved_bets) > 1
    assert len(set([bet.id for bet in resolved_bets])) == len(resolved_bets)

    # Verify that all bets convert to generic resolved bets.
    for bet in resolved_bets:
        bet.to_generic_resolved_bet()
