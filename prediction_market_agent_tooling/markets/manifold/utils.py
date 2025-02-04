from prediction_market_agent_tooling.markets.data_models import Resolution
from prediction_market_agent_tooling.markets.manifold.api import (
    get_manifold_binary_markets,
)


def find_resolution_on_manifold(question: str, n: int = 100) -> Resolution | None:
    # Even with exact-match search, Manifold doesn't return it as the first result, increase `n` if you can't find market that you know exists.
    manifold_markets = get_manifold_binary_markets(
        n, term=question, filter_=None, sort=None
    )
    for manifold_market in manifold_markets:
        if manifold_market.question == question:
            return manifold_market.resolution
    return None
