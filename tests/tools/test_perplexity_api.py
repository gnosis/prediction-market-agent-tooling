import pytest

from prediction_market_agent_tooling.config import APIKeys
from prediction_market_agent_tooling.markets.markets import (
    MarketType,
    get_binary_markets,
)
from prediction_market_agent_tooling.tools.perplexity.perplexity_search import (
    perplexity_search,
)
from tests.utils import RUN_PAID_TESTS


@pytest.mark.skipif(not RUN_PAID_TESTS, reason="This test costs money to run.")
def test_perplexity_api() -> None:
    markets = get_binary_markets(limit=1, market_type=MarketType.OMEN)
    question = f"Find relevant information about the following question: {markets[0].question}."
    result = perplexity_search(question, api_keys=APIKeys())

    assert result is not None
    assert result.content is not None
    assert result.citations is not None
    assert result.usage is not None
    assert result.usage["total_tokens"] > 0
    assert result.usage["prompt_tokens"] > 0
