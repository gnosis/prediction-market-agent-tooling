import tenacity
from web3 import Web3

from prediction_market_agent_tooling.markets.polymarket.polymarket_subgraph_handler import (
    MarketPosition,
    PolymarketSubgraphHandler,
)


@tenacity.retry(stop=tenacity.stop_after_attempt(5), wait=tenacity.wait_fixed(3))
def get_positions_from_recent_account(
    subgraph: PolymarketSubgraphHandler,
) -> list[MarketPosition]:
    """Query the subgraph for recent accounts and retrieve positions from one.

    Retries because The Graph indexers are intermittently unavailable
    for the marketPositions entity on this subgraph.
    """
    accounts = subgraph.conditions_subgraph.Query.accounts(
        first=10, orderBy="lastTradedTimestamp", orderDirection="desc"
    )
    result = subgraph.sg.query_json([accounts.id])
    items = subgraph._parse_items_from_json(result)
    assert len(items) > 0, "No accounts found in conditions subgraph"

    for item in items:
        user = Web3.to_checksum_address(item["id"])
        pos = subgraph.get_market_positions_from_user(first=10, user=user)
        if len(pos) > 0:
            return pos
    raise tenacity.TryAgain()


def test_get_positions() -> None:
    subgraph = PolymarketSubgraphHandler()
    pos = get_positions_from_recent_account(subgraph)
    assert pos[0].market.condition.id is not None
    assert pos[0].market.condition.outcomeSlotCount >= 2
