from prediction_market_agent_tooling.config import APIKeys
from prediction_market_agent_tooling.markets.polymarket.api import (
    get_user_positions,
    get_polymarkets_with_pagination,
)
from prediction_market_agent_tooling.markets.polymarket.polymarket_subgraph_handler import (
    PolymarketSubgraphHandler,
)
from prediction_market_agent_tooling.tools.hexbytes_custom import HexBytes


def test_get_positions(
    polymarket_subgraph_handler_test: PolymarketSubgraphHandler,
) -> None:
    # ToDo delete mes
    #  1. Fetch agent from market id
    keys = APIKeys()
    # c = ClobManager(keys)
    condition_id = HexBytes(
        "0x93317bbd26c133d3a28698c706fa051c8adcf5691b7179c861175a03a986b843"
    )
    # pos = get_user_positions(user_id=keys.public_key)
    pos = get_user_positions(user_id=keys.public_key, condition_ids=[condition_id])
    print("done")

    #  2. Fetch position
    market = get_polymarkets_with_pagination(
        limit=1,
    )
    #  3. assert not None
    assert False
