from prediction_market_agent_tooling.gtypes import HexBytes
from prediction_market_agent_tooling.markets.data_models import Resolution
from prediction_market_agent_tooling.markets.seer.seer_subgraph_handler import (
    SeerSubgraphHandler,
)


def test_resolution() -> None:
    resolved_market_id = HexBytes("0xd32068304199c1885b02d3ac91e0da06b9568409")
    market = SeerSubgraphHandler().get_market_by_id(market_id=resolved_market_id)
    resolution = market.get_resolution_enum()
    assert resolution == Resolution.YES
