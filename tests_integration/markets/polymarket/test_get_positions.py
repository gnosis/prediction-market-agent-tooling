from web3 import Web3

from prediction_market_agent_tooling.gtypes import ChecksumAddress
from prediction_market_agent_tooling.markets.polymarket.polymarket_subgraph_handler import (
    PolymarketSubgraphHandler,
)


def test_get_positions() -> None:
    subgraph = PolymarketSubgraphHandler()

    # Query the subgraph for any recent positions to find a user with positions.
    raw_positions = subgraph.conditions_subgraph.Query.marketPositions(first=5)
    user_fields = [raw_positions.user]
    result = subgraph.sg.query_json(user_fields)
    users: list[ChecksumAddress] = []
    for chunk in result:
        for v in chunk.values():
            if isinstance(v, list):
                users.extend(
                    Web3.to_checksum_address(item["user"]) for item in v if "user" in item
                )
            elif isinstance(v, dict) and "user" in v:
                users.append(Web3.to_checksum_address(v["user"]))
    assert len(users) > 0, "No positions found in conditions subgraph"

    # Now verify that get_market_positions_from_user returns valid results for a known user.
    user = users[0]
    pos = subgraph.get_market_positions_from_user(first=10, user=user)
    assert len(pos) > 0, f"Expected positions for user {user} but got none"
    assert pos[0].market.condition.id is not None
    assert pos[0].market.condition.outcomeSlotCount >= 2
    assert pos[0].user == user
