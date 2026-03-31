import tenacity
from web3 import Web3

from prediction_market_agent_tooling.markets.polymarket.polymarket_subgraph_handler import (
    MarketPosition,
    PolymarketSubgraphHandler,
)


@tenacity.retry(stop=tenacity.stop_after_attempt(3), wait=tenacity.wait_fixed(2))
def get_positions_from_recent_account(
    subgraph: PolymarketSubgraphHandler,
) -> list[MarketPosition]:
    """Query the subgraph for a recent account and retrieve its positions.

    Retries because The Graph indexers are intermittently unavailable
    for the marketPositions entity on this subgraph.
    """
    items = subgraph.query_subgraph(
        url=subgraph.conditions_subgraph_url,
        entity="accounts",
        fields="id",
        first=1,
        order_by="lastTradedTimestamp",
        order_direction="desc",
    )
    assert len(items) > 0, "No accounts found in conditions subgraph"

    user = Web3.to_checksum_address(items[0]["id"])
    pos = subgraph.get_market_positions_from_user(first=10, user=user)
    if len(pos) == 0:
        raise tenacity.TryAgain()
    return pos


def test_get_positions() -> None:
    subgraph = PolymarketSubgraphHandler()
    pos = get_positions_from_recent_account(subgraph)
    assert pos[0].market.condition.id is not None
    assert pos[0].market.condition.outcomeSlotCount >= 2
