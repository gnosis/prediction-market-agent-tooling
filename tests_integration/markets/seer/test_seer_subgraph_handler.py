import pytest
from web3 import Web3

from prediction_market_agent_tooling.gtypes import HexBytes
from prediction_market_agent_tooling.markets.agent_market import FilterBy, SortBy
from prediction_market_agent_tooling.markets.seer.data_models import SeerOutcomeEnum
from prediction_market_agent_tooling.markets.seer.seer_subgraph_handler import (
    SeerSubgraphHandler,
)
from prediction_market_agent_tooling.tools.utils import check_not_none

CONDITIONAL_MARKET_ID = HexBytes("0xfe2cc518b4d8c1d5db682db553c3de750d901ce0")
BINARY_MARKET_ID = HexBytes("0x7d72aa56ecdda207005fd7a02dbfd33f92d0def7")
BINARY_CONDITIONAL_MARKET_ID = HexBytes("0xbc82402814f7db8736980c0debb01df6aad8846e")


def test_get_all_seer_markets(seer_subgraph_handler_test: SeerSubgraphHandler) -> None:
    markets = seer_subgraph_handler_test.get_bicategorical_markets(
        filter_by=FilterBy.NONE
    )
    assert len(markets) > 1


def test_get_seer_market_by_id(seer_subgraph_handler_test: SeerSubgraphHandler) -> None:
    market_id = HexBytes("0x03cbd8e3a45c727643b015318fff883e13937fdd")
    market = seer_subgraph_handler_test.get_market_by_id(market_id)
    assert market is not None
    assert market.id == market_id


def test_conditional_market_not_retrieved(
    seer_subgraph_handler_test: SeerSubgraphHandler,
) -> None:
    markets = seer_subgraph_handler_test.get_bicategorical_markets(
        include_conditional_markets=False, filter_by=FilterBy.NONE
    )
    market_ids = [m.id for m in markets]
    assert CONDITIONAL_MARKET_ID not in market_ids


def test_conditional_market_retrieved(
    seer_subgraph_handler_test: SeerSubgraphHandler,
) -> None:
    markets = seer_subgraph_handler_test.get_bicategorical_markets(
        include_conditional_markets=True, filter_by=FilterBy.NONE
    )
    market_ids = [m.id for m in markets]
    assert CONDITIONAL_MARKET_ID in market_ids


def test_binary_market_retrieved(
    seer_subgraph_handler_test: SeerSubgraphHandler,
) -> None:
    markets = seer_subgraph_handler_test.get_binary_markets(
        include_conditional_markets=True, filter_by=FilterBy.NONE
    )
    market_ids = [m.id for m in markets]
    assert BINARY_MARKET_ID in market_ids
    assert BINARY_CONDITIONAL_MARKET_ID in market_ids


def test_get_pools_for_token(seer_subgraph_handler_test: SeerSubgraphHandler) -> None:
    us_election_market_id = HexBytes("0xa4b71ac2d0e17e1242e2d825e621acd18f0054ea")
    market = seer_subgraph_handler_test.get_market_by_id(us_election_market_id)
    # There must be pools for the Yes,No outcomes. We ignore the invalid outcome.
    for wrapped_token in market.wrapped_tokens[:-1]:
        pool = seer_subgraph_handler_test.get_pool_by_token(
            token_address=Web3.to_checksum_address(wrapped_token.lower()),
            collateral_address=market.collateral_token_contract_address_checksummed,
        )
        pool = check_not_none(pool)
        assert (
            pool.token0.id.hex().lower() == wrapped_token.lower()
            or pool.token1.id.hex().lower() == wrapped_token.lower()
        )


def test_get_binary_markets_newest_open(
    seer_subgraph_handler_test: SeerSubgraphHandler,
) -> None:
    # test method get_binary_markets
    markets = seer_subgraph_handler_test.get_binary_markets(
        sort_by=SortBy.NEWEST, filter_by=FilterBy.OPEN
    )
    # We expect at least 1 open markets
    assert len(markets) > 0
    assert not markets[0].is_resolved


@pytest.mark.parametrize(
    ("filter_by", "sort_by"),
    [
        (FilterBy.OPEN, SortBy.NEWEST),
        (FilterBy.NONE, SortBy.CLOSING_SOONEST),
        (FilterBy.RESOLVED, SortBy.HIGHEST_LIQUIDITY),
        (FilterBy.RESOLVED, SortBy.LOWEST_LIQUIDITY),
    ],
)
def test_binary_markets_retrieved(
    seer_subgraph_handler_test: SeerSubgraphHandler,
    filter_by: FilterBy,
    sort_by: SortBy,
) -> None:
    # test method get_binary_markets
    markets = seer_subgraph_handler_test.get_binary_markets(
        limit=1, sort_by=sort_by, filter_by=filter_by
    )
    # We expect at least 1 market for the given filter
    assert markets
