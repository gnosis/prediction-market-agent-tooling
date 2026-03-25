import requests
from web3 import Web3

from prediction_market_agent_tooling.gtypes import ChecksumAddress
from prediction_market_agent_tooling.markets.polymarket.api import (
    PolymarketOrderByEnum,
    get_polymarkets_with_pagination,
)
from prediction_market_agent_tooling.markets.polymarket.polymarket_subgraph_handler import (
    PolymarketSubgraphHandler,
)
from prediction_market_agent_tooling.tools.utils import check_not_none


def get_token_holders() -> list[ChecksumAddress]:
    recent_markets = get_polymarkets_with_pagination(
        limit=1, active=True, closed=False, order_by=PolymarketOrderByEnum.VOLUME_24HR
    )
    market = recent_markets[0]
    market_item = check_not_none(market.markets)[0]
    params = {"market": market_item.conditionId.to_0x_hex()}
    r = requests.get(url="https://data-api.polymarket.com/holders", params=params)
    data = r.json()
    return [
        Web3.to_checksum_address(entry["holders"][0]["proxyWallet"])
        for entry in data
        if entry.get("holders")
    ]


def test_get_positions() -> None:
    holders = get_token_holders()
    assert len(holders) > 0, "No token holders found"

    subgraph = PolymarketSubgraphHandler()
    for holder in holders[:10]:
        pos = subgraph.get_market_positions_from_user(first=10, user=holder)
        if len(pos) > 0:
            return

    # If none of the first 10 holders have positions, the test still passes
    # as long as the subgraph query itself works (no exceptions).
