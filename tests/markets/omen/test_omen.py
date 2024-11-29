import sys

import numpy as np
import pytest
from eth_account import Account
from eth_typing import HexAddress, HexStr
from web3 import Web3

from prediction_market_agent_tooling.gtypes import OutcomeStr, Wei, xDai
from prediction_market_agent_tooling.markets.agent_market import FilterBy, SortBy
from prediction_market_agent_tooling.markets.data_models import Position, TokenAmount
from prediction_market_agent_tooling.markets.omen.data_models import (
    OmenBet,
    OmenOutcomeToken,
    calculate_marginal_prices,
)
from prediction_market_agent_tooling.markets.omen.omen import (
    OmenAgentMarket,
    get_binary_market_p_yes_history,
    pick_binary_market,
)
from prediction_market_agent_tooling.markets.omen.omen_subgraph_handler import (
    OmenSubgraphHandler,
)
from prediction_market_agent_tooling.tools.betting_strategies.market_moving import (
    get_market_moving_bet,
)
from prediction_market_agent_tooling.tools.contract import ContractOnGnosisChain
from prediction_market_agent_tooling.tools.transaction_cache import (
    TransactionBlockCache,
)
from prediction_market_agent_tooling.tools.utils import (
    check_not_none,
    utc_datetime,
    utcnow,
)
from prediction_market_agent_tooling.tools.web3_utils import wei_to_xdai


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
        "0x2DD9f5678484C1F59F97eD334725858b938B4102"
    )
    positions = OmenAgentMarket.get_positions(user_id=user_address)
    liquid_positions = OmenAgentMarket.get_positions(
        user_id=user_address,
        liquid_only=True,
    )
    assert len(positions) > len(liquid_positions)

    # Get position id with smallest total amount
    min_position_id = min(positions, key=lambda x: x.total_amount.amount).market_id
    min_amount_position = next(
        position for position in positions if position.market_id == min_position_id
    )

    large_positions = OmenAgentMarket.get_positions(
        user_id=user_address, larger_than=min_amount_position.total_amount.amount
    )
    # Check that the smallest position has been filtered out
    assert len(large_positions) == len(positions) - 1
    assert all(position.market_id != min_position_id for position in large_positions)
    assert all(
        position.total_amount.amount > min_amount_position.total_amount.amount
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
        if token_balance.amount == 0:
            # The user has no position in this outcome
            continue
        assert token_balance.amount == position.amounts[OutcomeStr(outcome_str)].amount

    print(position)  # For extra test coverage


def test_positions_value() -> None:
    """
    Test that an artificial user position (generated based on a historical
    resolved bet) has the correct expected value, based on the bet's profit
    """
    user_address = Web3.to_checksum_address(
        "0x2DD9f5678484C1F59F97eD334725858b938B4102"
    )
    resolved_bets = OmenSubgraphHandler().get_resolved_bets_with_valid_answer(
        start_time=utc_datetime(2024, 3, 27, 4, 20),
        end_time=utc_datetime(2024, 3, 27, 4, 30),
        better_address=user_address,
    )
    assert len(resolved_bets) == 1
    bet = resolved_bets[0]
    assert bet.to_generic_resolved_bet().is_correct

    def bet_to_position(bet: OmenBet) -> Position:
        market = OmenAgentMarket.get_binary_market(bet.fpmm.id)
        outcome_str = OutcomeStr(market.get_outcome_str(bet.outcomeIndex))
        outcome_tokens = TokenAmount(
            amount=wei_to_xdai(Wei(bet.outcomeTokensTraded)),
            currency=OmenAgentMarket.currency,
        )
        return Position(market_id=market.id, amounts={outcome_str: outcome_tokens})

    positions = [bet_to_position(bet)]
    position_value = OmenAgentMarket.get_positions_value(positions=positions)

    bet_value_amount = bet.get_profit().amount + wei_to_xdai(bet.collateralAmount)
    assert np.isclose(
        position_value.amount,
        bet_value_amount,
        rtol=1e-3,  # relax tolerances due to fees
        atol=1e-3,
    )


def test_get_new_p_yes() -> None:
    market = OmenAgentMarket.get_binary_markets(
        limit=1,
        sort_by=SortBy.CLOSING_SOONEST,
        filter_by=FilterBy.OPEN,
    )[0]
    assert (
        market.get_new_p_yes(bet_amount=market.get_bet_amount(10.0), direction=True)
        > market.current_p_yes
    )
    assert (
        market.get_new_p_yes(bet_amount=market.get_bet_amount(11.0), direction=False)
        < market.current_p_yes
    )

    # Sanity check vs market moving bet
    target_p_yes = 0.95
    outcome_token_pool = check_not_none(market.outcome_token_pool)
    yes_outcome_pool_size = outcome_token_pool[market.get_outcome_str_from_bool(True)]
    no_outcome_pool_size = outcome_token_pool[market.get_outcome_str_from_bool(False)]
    bet = get_market_moving_bet(
        yes_outcome_pool_size=yes_outcome_pool_size,
        no_outcome_pool_size=no_outcome_pool_size,
        market_p_yes=market.current_p_yes,
        target_p_yes=0.95,
        fees=market.fees,
    )
    new_p_yes = market.get_new_p_yes(
        bet_amount=market.get_bet_amount(bet.size), direction=bet.direction
    )
    assert np.isclose(new_p_yes, target_p_yes)


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
    investment_amount = 5.0
    buy_direction = direction
    for market in markets:
        buy_amount0 = market.get_buy_token_amount(
            bet_amount=market.get_bet_amount(investment_amount),
            direction=buy_direction,
        ).amount
        buy_amount1 = market._get_buy_token_amount_from_smart_contract(
            bet_amount=market.get_bet_amount(investment_amount),
            direction=buy_direction,
        ).amount
        assert np.isclose(buy_amount0, buy_amount1)


@pytest.mark.parametrize(
    "outcome_token_amounts, expected_marginal_prices",
    [
        ([0, 100], None),
        ([1000, 1000], [0.5, 0.5]),
        ([500, 1500], [0.75, 0.25]),
    ],
)
def test_calculate_marginal_prices(
    outcome_token_amounts: list[OmenOutcomeToken],
    expected_marginal_prices: list[xDai] | None,
) -> None:
    assert calculate_marginal_prices(outcome_token_amounts) == expected_marginal_prices


def test_get_most_recent_trade_datetime() -> None:
    """
    Tests that `get_most_recent_trade_datetime` returns the correct datetime
    from all possible trade datetimes.
    """
    market = OmenAgentMarket.from_data_model(pick_binary_market())
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
        bet for bet in resolved_bets if bet.outcomeTokensTraded == 6906257886585173059
    ][0]
    generic_bet = selected_bet.to_generic_resolved_bet()

    tx_cache = TransactionBlockCache(ContractOnGnosisChain.get_web3())
    bet_block_number = tx_cache.get_block_number(selected_bet.transactionHash.hex())

    assert np.isclose(
        generic_bet.amount.amount, 4.50548
    ), f"{generic_bet.amount} != 4.50548"
    assert np.isclose(
        generic_bet.profit.amount, 2.4007766133282686
    ), f"{generic_bet.profit.amount} != 2.4007766133282686"

    # We need to substract -1 from block number, to get the market in the state before actually doing that bet --> after it's done, results are different
    market_before_placing_bet = OmenAgentMarket.from_data_model(
        OmenSubgraphHandler().get_omen_market_by_market_id(
            market_id=market_id, block_number=bet_block_number - 1
        )
    )
    would_get_outcome_tokens = market_before_placing_bet.get_buy_token_amount(
        bet_amount=generic_bet.amount, direction=generic_bet.outcome
    )

    assert would_get_outcome_tokens.amount == wei_to_xdai(
        selected_bet.outcomeTokensTraded
    ), f"{would_get_outcome_tokens.amount} != {selected_bet.collateral_amount_usd}"
