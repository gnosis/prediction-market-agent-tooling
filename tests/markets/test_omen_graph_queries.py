from prediction_market_agent_tooling.config import APIKeys
from prediction_market_agent_tooling.markets.omen.omen_graph_queries import (
    get_user_positions,
)


def test_get_user_positions() -> None:
    keys = APIKeys()
    user_positions = get_user_positions(keys.bet_from_address)
    # We assume that the agent has at least 1 historical position
    assert len(user_positions) > 1
