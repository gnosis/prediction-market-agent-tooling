import pytest

from prediction_market_agent_tooling.markets.omen.omen_subgraph_handler import (
    OmenSubgraphHandler,
)


@pytest.fixture(scope="module")
def a_bet_from_address() -> str:
    return "0x3666DA333dAdD05083FEf9FF6dDEe588d26E4307"


@pytest.fixture(scope="module")
def agent0_address() -> str:
    return "0x2DD9f5678484C1F59F97eD334725858b938B4102"


@pytest.fixture(scope="session")
def omen_subgraph_handler() -> OmenSubgraphHandler:
    return OmenSubgraphHandler()
