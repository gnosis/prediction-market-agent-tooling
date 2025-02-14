from prediction_market_agent_tooling.gtypes import HexBytes
from prediction_market_agent_tooling.markets.agent_market import FilterBy
from prediction_market_agent_tooling.markets.seer.seer_subgraph_handler import (
    SeerSubgraphHandler,
)

CONDITIONAL_MARKET_ID = HexBytes("0xe12f48ecdd6e64d95d1d8f1d5d7aa37e14f2888b")
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


def test_get_pools_for_market(seer_subgraph_handler_test: SeerSubgraphHandler) -> None:
    us_election_market_id = HexBytes("0x43d881f5920ed29fc5cd4917d6817496abbba6d9")
    market = seer_subgraph_handler_test.get_market_by_id(us_election_market_id)

    pools = seer_subgraph_handler_test.get_swapr_pools_for_market(market)
    assert len(pools) > 1
    for pool in pools:
        # one of the tokens must be a wrapped token
        assert (
            pool.token0.id.hex() in market.wrapped_tokens
            or pool.token1.id.hex() in market.wrapped_tokens
        )
