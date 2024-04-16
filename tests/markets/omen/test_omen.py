from datetime import timedelta

import numpy as np
import pytest
from eth_typing import HexAddress, HexStr
from loguru import logger
from web3 import Web3

from prediction_market_agent_tooling.config import APIKeys
from prediction_market_agent_tooling.gtypes import DatetimeWithTimezone, xdai_type
from prediction_market_agent_tooling.markets.agent_market import FilterBy, SortBy
from prediction_market_agent_tooling.markets.data_models import Currency, TokenAmount
from prediction_market_agent_tooling.markets.omen.omen import (
    OMEN_FALSE_OUTCOME,
    OMEN_TRUE_OUTCOME,
    OmenAgentMarket,
    binary_omen_buy_outcome_tx,
    binary_omen_sell_outcome_tx,
    omen_create_market_tx,
    omen_fund_market_tx,
    omen_redeem_full_position_tx,
    omen_remove_fund_market_tx,
    pick_binary_market,
)
from prediction_market_agent_tooling.markets.omen.omen_subgraph_handler import (
    OmenSubgraphHandler,
)
from prediction_market_agent_tooling.tools.contract import wait_until_nonce_changed
from prediction_market_agent_tooling.tools.utils import check_not_none, utcnow
from prediction_market_agent_tooling.tools.web3_utils import xdai_to_wei
from tests.utils import RUN_PAID_TESTS


def test_omen_pick_binary_market() -> None:
    market = pick_binary_market()
    assert market.outcomes == [
        "Yes",
        "No",
    ], "Omen binary market should have two outcomes, Yes and No."


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
    with wait_until_nonce_changed(keys.bet_from_address):
        binary_omen_buy_outcome_tx(
            amount=buy_amount,
            from_private_key=keys.bet_from_private_key,
            market=market,
            binary_outcome=True,
            auto_deposit=True,
        )
    with wait_until_nonce_changed(keys.bet_from_address):
        binary_omen_sell_outcome_tx(
            amount=sell_amount,
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
        question="Will GNO hit $1000 in 2 minutes from creation of this market?",
        closing_time=utcnow() + timedelta(minutes=2),
        category="cryptocurrency",
        language="en",
        from_private_key=keys.bet_from_private_key,
        outcomes=[OMEN_TRUE_OUTCOME, OMEN_FALSE_OUTCOME],
        auto_deposit=True,
    )


@pytest.mark.skipif(not RUN_PAID_TESTS, reason="This test costs money to run.")
def test_omen_fund_and_remove_fund_market() -> None:
    # You can double check your address at https://gnosisscan.io/ afterwards or at the market's address.
    market = OmenAgentMarket.from_data_model(pick_binary_market())
    logger.debug(
        "Fund and remove funding market test address:",
        market.market_maker_contract_address_checksummed,
    )

    funds = xdai_to_wei(xdai_type(0.1))
    remove_fund = xdai_to_wei(xdai_type(0.01))
    keys = APIKeys()
    with wait_until_nonce_changed(keys.bet_from_address):
        omen_fund_market_tx(
            market=market,
            funds=funds,
            from_private_key=keys.bet_from_private_key,
            auto_deposit=True,
        )
    with wait_until_nonce_changed(keys.bet_from_address):
        omen_remove_fund_market_tx(
            market=market,
            shares=remove_fund,
            from_private_key=keys.bet_from_private_key,
        )


def test_p_yes() -> None:
    # Find a market with outcomeTokenMarginalPrices and verify that p_yes is correct.
    for m in OmenSubgraphHandler().get_omen_binary_markets_simple(
        limit=200,
        sort_by=SortBy.NEWEST,
        filter_by=FilterBy.OPEN,
    ):
        if m.outcomeTokenProbabilities is not None:
            market = m
            break
    assert market is not None, "No market found with outcomeTokenProbabilities."
    assert np.isclose(market.p_yes, check_not_none(market.outcomeTokenProbabilities)[0])


@pytest.mark.skipif(not RUN_PAID_TESTS, reason="This test costs money to run.")
def test_omen_redeem_positions() -> None:
    market_id = (
        "0x6469da5478e5b2ddf9f6b7fba365e5670b7880f4".lower()
    )  # Market on which agent previously betted on
    subgraph_handler = OmenSubgraphHandler()
    market_data_model = subgraph_handler.get_omen_market_by_market_id(
        market_id=HexAddress(HexStr(market_id))
    )
    market = OmenAgentMarket.from_data_model(market_data_model)
    keys = APIKeys()
    omen_redeem_full_position_tx(
        market=market,
        from_private_key=keys.bet_from_private_key,
    )


@pytest.mark.skipif(not RUN_PAID_TESTS, reason="This test costs money to run.")
def create_market_fund_market_remove_funding() -> None:
    """
    ToDo - Once we have tests running in an isolated blockchain, write this test as follows:
        - Create a new market
        - Fund the market with amount
        - Assert balanceOf(creator) == amount
        - (Optionally) Close the market
        - Remove funding
        - Assert amount in xDAI is reflected in user's balance
    """
    assert True


def test_omen_market_close_time() -> None:
    """
    Get open markets sorted by 'closing_soonest'. Verify that:
    - close time is after open time
    - close time is in the future
    - close time is in ascending order
    """
    time_now = utcnow()
    markets = [
        OmenAgentMarket.from_data_model(m)
        for m in OmenSubgraphHandler().get_omen_binary_markets_simple(
            limit=100,
            sort_by=SortBy.CLOSING_SOONEST,
            filter_by=FilterBy.OPEN,
        )
    ]
    for market in markets:
        assert (
            market.close_time > market.created_time
        ), "Market close time should be after open time."
        assert (
            market.close_time >= time_now
        ), "Market close time should be in the future."
        time_now = DatetimeWithTimezone(
            market.close_time
        )  # Ensure close time is in ascending order


def test_market_liquidity() -> None:
    """
    Get open markets sorted by 'closing soonest'. Verify that liquidity is
    greater than 0
    """
    markets = OmenAgentMarket.get_binary_markets(
        limit=10,
        sort_by=SortBy.CLOSING_SOONEST,
        filter_by=FilterBy.OPEN,
    )
    for market in markets:
        assert type(market) == OmenAgentMarket
        assert (
            market.get_liquidity_in_xdai() > 0
        ), "Market liquidity should be greater than 0."


def test_get_binary_market() -> None:
    id = "0x0020d13c89140b47e10db54cbd53852b90bc1391"
    market = OmenAgentMarket.get_binary_market(id)
    assert market.id == id


def test_balance_for_user_in_market() -> None:
    user_address = Web3.to_checksum_address(
        "0x2DD9f5678484C1F59F97eD334725858b938B4102"
    )
    market_id = "0x59975b067b0716fef6f561e1e30e44f606b08803"
    market = OmenAgentMarket.get_binary_market(market_id)
    balance_yes: TokenAmount = market.get_token_balance(
        user_id=user_address,
        outcome=OMEN_TRUE_OUTCOME,
    )
    assert balance_yes.currency == Currency.xDai
    assert float(balance_yes.amount) == 0

    balance_no = market.get_token_balance(
        user_id=user_address,
        outcome=OMEN_FALSE_OUTCOME,
    )
    assert balance_no.currency == Currency.xDai
    assert float(balance_no.amount) == 0
