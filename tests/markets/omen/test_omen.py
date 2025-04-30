import sys

import numpy as np
import pytest
from eth_account import Account
from eth_typing import ChecksumAddress, HexAddress, HexStr
from web3 import Web3

from prediction_market_agent_tooling.gtypes import USD, CollateralToken
from prediction_market_agent_tooling.markets.agent_market import FilterBy, SortBy
from prediction_market_agent_tooling.markets.omen.data_models import (
    OmenBet,
    OmenMarket,
    OutcomeWei,
    calculate_marginal_prices,
)
from prediction_market_agent_tooling.markets.omen.omen import (
    OmenAgentMarket,
    get_binary_market_p_yes_history,
)
from prediction_market_agent_tooling.markets.omen.omen_subgraph_handler import (
    SAFE_COLLATERAL_TOKENS_ADDRESSES,
    OmenSubgraphHandler,
)
from prediction_market_agent_tooling.tools.contract import ContractOnGnosisChain
from prediction_market_agent_tooling.tools.transaction_cache import (
    TransactionBlockCache,
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
        time_now = market.close_time  # Ensure close time is in ascending order


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

    Also check that `larger_than` and `liquid_only` filters work
    """
    # Pick a user that has active positions
    user_address = Web3.to_checksum_address(
        "0xf758C18402ddEf2d231911C4C326Aa46510788f0"
    )
    positions = OmenAgentMarket.get_positions(user_id=user_address)
    liquid_positions = OmenAgentMarket.get_positions(
        user_id=user_address,
        liquid_only=True,
    )
    assert len(positions) > len(liquid_positions)

    # Get position id with smallest total amount
    min_position_id = min(positions, key=lambda x: x.total_amount_ot).market_id
    min_amount_position = next(
        position for position in positions if position.market_id == min_position_id
    )

    large_positions = OmenAgentMarket.get_positions(
        user_id=user_address, larger_than=min_amount_position.total_amount_ot
    )
    # conflicting positions
    # 1 - ExistingPosition(market_id='0x3cab82a2cce239bd4ad3b0620be32b4409fd74c0', amounts_current={'No': USD(1.2833016323746e-05)}, amounts_potential={'No': USD(1.2833016323746e-05)}, amounts_ot={'No': OutcomeToken(1.2833016323746e-05)})
    # 2 (min from above) - ExistingPosition(market_id='0x626002415eef1117ba0257fc4d2f70753550bbb3', amounts_current={'No': USD(1.4388460783717888e-05)}, amounts_potential={'No': USD(1.4388460783717888e-05)}, amounts_ot={'No': OutcomeToken(1.2249484218406e-05)})
    # Check that the smallest position has been filtered out
    assert all(position.market_id != min_position_id for position in large_positions)
    assert all(
        position.total_amount_ot > min_amount_position.total_amount_ot
        for position in large_positions
    )

    # Pick a single position to test, otherwise it can be very slow
    position = positions[0]

    market = OmenAgentMarket.get_binary_market(position.market_id)
    for outcome_str in market.outcomes:
        token_balance = market.get_token_balance(
            user_id=user_address,
            outcome=outcome_str,
        )
        if not token_balance:
            # The user has no position in this outcome
            continue
        assert token_balance == position.amounts_ot[outcome_str]

    print(position)  # For extra test coverage


@pytest.mark.parametrize("direction", [True, False])
def test_get_buy_token_amount(direction: bool) -> None:
    """
    Test that the two methods of calculating buy amount are equivalent for a
    'live' market (i.e. where the token pool matches that of the current smart
    contract state)
    """
    markets = OmenAgentMarket.get_binary_markets(
        limit=10,
        sort_by=SortBy.CLOSING_SOONEST,
        filter_by=FilterBy.OPEN,
    )
    investment_amount = USD(5)
    for market in markets:
        outcome_str = market.get_outcome_str_from_bool(direction)
        buy_amount0 = market.get_buy_token_amount(
            bet_amount=investment_amount,
            outcome=outcome_str,
        )
        buy_amount1 = market._get_buy_token_amount_from_smart_contract(
            bet_amount=investment_amount,
            outcome=outcome_str,
        )
        assert np.isclose(buy_amount0.value, buy_amount1.value)


@pytest.mark.parametrize(
    "outcome_token_amounts, expected_marginal_prices",
    [
        ([0, 100], None),
        ([1000, 1000], [0.5, 0.5]),
        ([500, 1500], [0.75, 0.25]),
    ],
)
def test_calculate_marginal_prices(
    outcome_token_amounts: list[int],
    expected_marginal_prices: list[float] | None,
) -> None:
    assert calculate_marginal_prices(
        [OutcomeWei(x) for x in outcome_token_amounts]
    ) == (
        [CollateralToken(x) for x in expected_marginal_prices]
        if expected_marginal_prices
        else None
    )


def test_get_most_recent_trade_datetime() -> None:
    """
    Tests that `get_most_recent_trade_datetime` returns the correct datetime
    from all possible trade datetimes.
    """

    user_id = Web3.to_checksum_address(
        "0x2DD9f5678484C1F59F97eD334725858b938B4102"
    )  # A user with trade history

    sgh = OmenSubgraphHandler()
    market_id = Web3.to_checksum_address("0x1e0e1d092bffebfb4fa90eeba7bfeddcebc9751c")
    trades: list[OmenBet] = sgh.get_trades(
        limit=sys.maxsize,
        better_address=user_id,
        market_id=market_id,
    )
    market = OmenAgentMarket.get_binary_market(id=market_id)
    assert len(trades) > 2, "We have made multiple trades in this market"

    assert len(set(trade.creation_datetime for trade in trades)) == len(
        trades
    ), "All trades have unique timestamps"
    most_recent_trade_0 = max(trades, key=lambda x: x.creation_datetime)
    most_recent_trade_datetime_1 = check_not_none(
        market.get_most_recent_trade_datetime(user_id=user_id)
    )
    assert most_recent_trade_0.creation_datetime == most_recent_trade_datetime_1


def test_get_outcome_tokens_in_the_past() -> None:
    """
    Test that `get_buy_token_amount` on market from block one before the one where bet is placed gives the same results as bet's `collateral_amount_usd`.
    """
    user_address = Web3.to_checksum_address(
        "0x7d3A0DA18e14CCb63375cdC250E8A8399997816F"
    )
    market_id = Web3.to_checksum_address("0x07f30370e60c38d5099ef3d8fc44600de77e2104")
    resolved_bets = OmenSubgraphHandler().get_resolved_bets_with_valid_answer(
        market_id=market_id,
        better_address=user_address,
    )
    selected_bet = [
        bet
        for bet in resolved_bets
        if bet.outcomeTokensTraded == OutcomeWei(6906257886585173059)
    ][0]
    generic_bet = selected_bet.to_generic_resolved_bet()

    tx_cache = TransactionBlockCache(ContractOnGnosisChain.get_web3())
    bet_block_number = tx_cache.get_block_number(selected_bet.transactionHash.hex())

    assert np.isclose(
        generic_bet.amount.value, 4.50548
    ), f"{generic_bet.amount} != 4.50548"
    assert np.isclose(
        generic_bet.profit.value, 2.4007766133282686
    ), f"{generic_bet.profit} != 2.4007766133282686"

    # We need to subtract -1 from block number, to get the market in the state before actually doing that bet --> after it's done, results are different
    market_before_placing_bet = OmenAgentMarket.from_data_model(
        OmenSubgraphHandler().get_omen_market_by_market_id(
            market_id=market_id, block_number=bet_block_number - 1
        )
    )

    would_get_outcome_tokens = market_before_placing_bet.get_buy_token_amount(
        bet_amount=generic_bet.amount, outcome=generic_bet.outcome
    )

    assert would_get_outcome_tokens == selected_bet.outcomeTokensTraded.as_outcome_token


def pick_binary_market(
    sort_by: SortBy = SortBy.CLOSING_SOONEST,
    filter_by: FilterBy = FilterBy.OPEN,
    collateral_token_address_in: (
        tuple[ChecksumAddress, ...] | None
    ) = SAFE_COLLATERAL_TOKENS_ADDRESSES,
) -> OmenMarket:
    subgraph_handler = OmenSubgraphHandler()
    return subgraph_handler.get_omen_binary_markets_simple(
        limit=1,
        sort_by=sort_by,
        filter_by=filter_by,
        collateral_token_address_in=collateral_token_address_in,
        include_categorical_markets=False,
    )[0]
