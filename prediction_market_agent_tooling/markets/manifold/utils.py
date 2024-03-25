from prediction_market_agent_tooling.markets.data_models import Resolution
from prediction_market_agent_tooling.markets.manifold.api import (
    get_manifold_binary_markets,
)


def find_resolution_on_manifold(question: str) -> Resolution | None:
    manifold_markets = get_manifold_binary_markets(
        10, term=question, filter_=None, sort=None
    )
    for manifold_market in manifold_markets:
        if manifold_market.question == question:
            return manifold_market.resolution
    return None
