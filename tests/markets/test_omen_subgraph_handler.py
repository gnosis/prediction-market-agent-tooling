from datetime import datetime

import pytest
from eth_typing import HexAddress, HexStr
from web3 import Web3

from prediction_market_agent_tooling.markets.agent_market import SortBy, FilterBy
from prediction_market_agent_tooling.markets.omen.omen_subgraph_handler import (
    OmenSubgraphHandler,
)


@pytest.fixture()
def omen_subgraph_handler():
    return OmenSubgraphHandler()


def test_omen_get_market(omen_subgraph_handler: OmenSubgraphHandler) -> None:
    market = omen_subgraph_handler.get_omen_market(
        HexAddress(HexStr("0xa3e47bb771074b33f2e279b9801341e9e0c9c6d7"))
    )
    assert (
        market.title
        == "Will Bethesda's 'Indiana Jones and the Great Circle' be released by January 25, 2024?"
    ), "Omen market question doesn't match the expected value."


def test_resolved_omen_bets(
    a_bet_from_address: str, omen_subgraph_handler: OmenSubgraphHandler
) -> None:
    better_address = Web3.to_checksum_address(a_bet_from_address)
    resolved_bets = omen_subgraph_handler.get_resolved_bets(
        start_time=datetime(2024, 2, 20),
        end_time=datetime(2024, 2, 28),
        better_address=better_address,
    )

    # Verify that the bets are unique.
    assert len(resolved_bets) > 1
    assert len(set([bet.id for bet in resolved_bets])) == len(resolved_bets)

    # Verify that all bets convert to generic resolved bets.
    for bet in resolved_bets:
        bet.to_generic_resolved_bet()


def test_get_bets(
    a_bet_from_address: str, omen_subgraph_handler: OmenSubgraphHandler
) -> None:
    better_address = Web3.to_checksum_address(a_bet_from_address)
    bets = omen_subgraph_handler.get_bets(
        start_time=datetime(2024, 2, 20),
        end_time=datetime(2024, 2, 21),
        better_address=better_address,
    )
    assert len(bets) == 1
    assert (
        bets[0].id
        == "0x5b1457bb7525eed03d3c78a542ce6d89be6090e10x3666da333dadd05083fef9ff6ddee588d26e43070x1"
    )


def test_filter_open_markets(omen_subgraph_handler: OmenSubgraphHandler) -> None:
    # ToDo
    limit = 100

    markets = omen_subgraph_handler.get_omen_markets(
        limit=limit,
        sort_by=SortBy.NEWEST,
        filter_by=FilterBy.OPEN,
    )
    assert len(markets) == limit
    for market in markets:
        assert market.is_open


def test_filter_resolved_markets(omen_subgraph_handler: OmenSubgraphHandler) -> None:
    limit = 10
    markets = omen_subgraph_handler.get_omen_markets(
        limit=limit,
        sort_by=SortBy.CLOSING_SOONEST,
        filter_by=FilterBy.RESOLVED,
    )
    assert len(markets) == limit
    for market in markets:
        assert market.is_resolved


def test_get_user_positions(
    agent0_address: str, omen_subgraph_handler: OmenSubgraphHandler
) -> None:
    better_address = Web3.to_checksum_address(HexAddress(HexStr(agent0_address)))
    user_positions = omen_subgraph_handler.get_user_positions(better_address)
    # We assume that the agent has at least 1 historical position
    assert len(user_positions) > 1
