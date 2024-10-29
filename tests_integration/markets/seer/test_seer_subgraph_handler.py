import typing as t

import pytest

from prediction_market_agent_tooling.markets.seer.seer_subgraph_handler import (
    SeerSubgraphHandler,
)
from prediction_market_agent_tooling.tools.hexbytes_custom import HexBytes


@pytest.fixture(scope="module")
def handler() -> t.Generator[SeerSubgraphHandler, None, None]:
    yield SeerSubgraphHandler()


def test_get_all_seer_markets(handler: SeerSubgraphHandler) -> None:
    markets = handler.get_binary_markets()
    assert len(markets) > 1


def test_get_seer_market_by_id(handler: SeerSubgraphHandler) -> None:
    market_id = HexBytes("0x03cbd8e3a45c727643b015318fff883e13937fdd")
    market = handler.get_market_by_id(market_id)
    assert market is not None
    assert market.id == market_id


def test_conditional_market_not_retrieved(handler: SeerSubgraphHandler) -> None:
    conditional_market_id = HexBytes("0xe12f48ecdd6e64d95d1d8f1d5d7aa37e14f2888b")
    markets = handler.get_binary_markets()
    market_ids = [m.id for m in markets]
    assert conditional_market_id not in market_ids


def test_get_pools_for_market(handler: SeerSubgraphHandler) -> None:
    us_election_market_id = HexBytes("0x43d881f5920ed29fc5cd4917d6817496abbba6d9")
    market = handler.get_market_by_id(us_election_market_id)

    pools = handler.get_pools_for_market(market)
    assert len(pools) > 1
    for pool in pools:
        # one of the tokens must be a wrapped token
        assert (
            pool.token0.id in market.wrapped_tokens
            or pool.token1.id in market.wrapped_tokens
        )
