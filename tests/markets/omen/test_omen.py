import numpy as np
from eth_account import Account
from eth_typing import HexAddress, HexStr
from web3 import Web3

from prediction_market_agent_tooling.gtypes import DatetimeWithTimezone, OutcomeStr
from prediction_market_agent_tooling.markets.agent_market import FilterBy, SortBy
from prediction_market_agent_tooling.markets.omen.omen import (
    OmenAgentMarket,
    get_binary_market_p_yes_history,
    pick_binary_market,
)
from prediction_market_agent_tooling.markets.omen.omen_subgraph_handler import (
    OmenSubgraphHandler,
)
from prediction_market_agent_tooling.tools.utils import check_not_none, utcnow


def test_omen_pick_binary_market() -> None:
    market = pick_binary_market()
    assert market.outcomes == [
        "Yes",
        "No",
    ], "Omen binary market should have two outcomes, Yes and No."


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
    assert np.isclose(
        market.current_p_yes, check_not_none(market.outcomeTokenProbabilities)[0]
    )


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
        assert market.has_liquidity()


def test_can_be_traded() -> None:
    id = "0x0020d13c89140b47e10db54cbd53852b90bc1391"  # A known resolved market
    market = OmenAgentMarket.get_binary_market(id)
    assert not market.can_be_traded()


def test_get_binary_market() -> None:
    id = "0x0020d13c89140b47e10db54cbd53852b90bc1391"
    market = OmenAgentMarket.get_binary_market(id)
    assert market.id == id


def test_get_binary_market_p_yes_history() -> None:
    market = OmenSubgraphHandler().get_omen_market_by_market_id(
        HexAddress(HexStr("0x934b9f379dd9d8850e468df707d58711da2966cd"))
    )
    agent_market = OmenAgentMarket.from_data_model(market)
    history = get_binary_market_p_yes_history(agent_market)
    assert len(history) > 0
    assert all(0 <= 0 <= 1.0 for x in history)
    assert history[0] == 0.5


def test_get_positions_0() -> None:
    """
    Create a new account and verify that there are no positions for the account
    """
    user_id = Account.create().address
    positions = OmenAgentMarket.get_positions(user_id=user_id)
    assert len(positions) == 0


def test_get_positions_1() -> None:
    """
    Check the user's positions against 'market.get_token_balance'
    """
    # Pick a user that has active positions
    user_address = Web3.to_checksum_address(
        "0x2DD9f5678484C1F59F97eD334725858b938B4102"
    )
    positions = OmenAgentMarket.get_positions(user_id=user_address)
    liquid_positions = OmenAgentMarket.get_positions(
        user_id=user_address,
        liquid_only=True,
    )
    assert len(positions) > len(liquid_positions)

    # Pick a single position to test, otherwise it can be very slow
    position = positions[0]

    market = OmenAgentMarket.get_binary_market(position.market_id)
    for outcome_str in market.outcomes:
        token_balance = market.get_token_balance(
            user_id=user_address,
            outcome=outcome_str,
        )
        if token_balance.amount == 0:
            # The user has no position in this outcome
            continue
        assert token_balance.amount == position.amounts[OutcomeStr(outcome_str)].amount

    print(position)  # For extra test coverage


def test_positions_value() -> None:
    # Pick a user that has active positions
    user_address = Web3.to_checksum_address(
        "0x2DD9f5678484C1F59F97eD334725858b938B4102"
    )
    positions = OmenAgentMarket.get_positions(user_id=user_address)
    value = OmenAgentMarket.get_positions_value(positions=positions)
    assert value.amount > 0
