import typing as t

import pytest

from prediction_market_agent_tooling.markets.seer.seer_subgraph_handler import (
    SeerSubgraphHandler,
)


@pytest.fixture(scope="module")
def seer_subgraph_handler_test() -> t.Generator[SeerSubgraphHandler, None, None]:
    yield SeerSubgraphHandler()
