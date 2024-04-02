import sys
from datetime import datetime

from eth_typing import HexAddress, HexStr
from web3 import Web3

from prediction_market_agent_tooling.markets.agent_market import FilterBy, SortBy
from prediction_market_agent_tooling.markets.omen.omen_subgraph_handler import (
    OmenSubgraphHandler,
)
from prediction_market_agent_tooling.tools.hexbytes_custom import HexBytes


def test_omen_get_market(omen_subgraph_handler: OmenSubgraphHandler) -> None:
    market = omen_subgraph_handler.get_omen_market(
        HexAddress(HexStr("0xa3e47bb771074b33f2e279b9801341e9e0c9c6d7"))
    )
    assert (
        market.title
        == "Will Bethesda's 'Indiana Jones and the Great Circle' be released by January 25, 2024?"
    ), "Omen market question doesn't match the expected value."


def test_markets_with_outcome_null(omen_subgraph_handler: OmenSubgraphHandler) -> None:
    markets = omen_subgraph_handler.get_omen_binary_markets(
        limit=sys.maxsize, filter_by=FilterBy.NONE, sort_by=SortBy.NONE
    )
    for market in markets:
        assert isinstance(market.outcomes, list)


def test_markets_with_creation_timestamp_between(
    omen_subgraph_handler: OmenSubgraphHandler,
) -> None:
    creator = "0x95aa7cc38f8ff36efecf2fefa6f4850320dd32f7"
    expected_trade_id = "0x004469fa6abc620479ca3006199c00f74bd388ef0x95aa7cc38f8ff36efecf2fefa6f4850320dd32f70x29"
    bets = omen_subgraph_handler.get_bets(
        better_address=Web3.to_checksum_address(creator),
        filter_by_answer_finalized_not_null=False,
        start_time=datetime.fromtimestamp(1625073159),
        end_time=datetime.fromtimestamp(1625073162),
    )
    assert len(bets) == 1
    bet = bets[0]
    assert bet.id == expected_trade_id


def test_get_markets_exclude_questions(
    omen_subgraph_handler: OmenSubgraphHandler,
) -> None:
    excluded_question_titles = [
        "Belgium v Italy - Who will win this UEFA Euro 2020 Quarter-Finals match?",
        "Will the Grayscale Ethereum Trust (ETHE) have a discount to NAV at the end of September 2021?",
    ]
    markets = omen_subgraph_handler.get_omen_binary_markets(
        excluded_questions=set(excluded_question_titles),
        filter_by=FilterBy.NONE,
        sort_by=SortBy.NONE,
        limit=sys.maxsize,
    )

    for m in markets:
        assert m.question.title not in excluded_question_titles


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

    markets = omen_subgraph_handler.get_omen_binary_markets(
        limit=limit,
        sort_by=SortBy.NEWEST,
        filter_by=FilterBy.OPEN,
    )
    assert len(markets) == limit
    for market in markets:
        assert market.is_open


def test_filter_resolved_markets(omen_subgraph_handler: OmenSubgraphHandler) -> None:
    limit = 10
    markets = omen_subgraph_handler.get_omen_binary_markets(
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


def test_get_answers(omen_subgraph_handler: OmenSubgraphHandler) -> None:
    question_id = HexBytes.fromhex(
        HexStr("0xdcb2691a9ec05e25a6e595a9972b482ea65b789d978b27c0c06ff97345fce919")
    )
    answers = omen_subgraph_handler.get_answers(question_id)
    assert len(answers) == 1
    answer = answers[0]
    assert answer.question.user == HexAddress(
        HexStr("0xdaa72a1944191a15e92218d9f00c375a8607a568")
    )
