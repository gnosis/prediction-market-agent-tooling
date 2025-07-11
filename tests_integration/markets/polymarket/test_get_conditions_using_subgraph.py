from prediction_market_agent_tooling.gtypes import HexBytes
from prediction_market_agent_tooling.markets.polymarket.polymarket_subgraph_handler import (
    PolymarketSubgraphHandler,
)


def test_get_conditions_using_subgraph() -> None:
    s = PolymarketSubgraphHandler()
    condition_ids = [
        HexBytes(
            "0xfc7c7189f8ca61dab1caa934a4f0fcd8d3ec7b5373564063ca90b5963aacf441"  # web3-private-key-ok
        ),
        HexBytes(
            "0xb86f59208df00409351d8786283aae7fa8eab197b316cd095e57513b70575681"  # web3-private-key-ok
        ),
    ]
    conditions = s.get_conditions(condition_ids=condition_ids)
    assert len(conditions) == len(condition_ids)
