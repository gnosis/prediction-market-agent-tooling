import typing as t

import pytest

from prediction_market_agent_tooling.markets.polymarket.polymarket_subgraph_handler import (
    PolymarketSubgraphHandler,
)


@pytest.fixture(scope="module")
def polymarket_subgraph_handler_test() -> (
    t.Generator[PolymarketSubgraphHandler, None, None]
):
    yield PolymarketSubgraphHandler()
