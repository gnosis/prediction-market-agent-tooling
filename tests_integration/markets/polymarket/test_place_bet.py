import pytest

from prediction_market_agent_tooling.gtypes import USD
from prediction_market_agent_tooling.markets.polymarket.polymarket import (
    PolymarketAgentMarket,
)
from tests.utils import RUN_PAID_TESTS


@pytest.mark.skipif(not RUN_PAID_TESTS, reason="This test costs money to run.")
def test_place_bet_real() -> None:
    """Place a real $1 bet on Polymarket.

    Requires RUN_PAID_TESTS=1 and BET_FROM_PRIVATE_KEY with USDC on Polygon.
    This is the only way to fully validate the CLOB integration end-to-end.
    """
    markets = PolymarketAgentMarket.get_markets(limit=5)
    # Pick the first tradeable market
    market = next(m for m in markets if m.can_be_traded())

    tx_hash = market.place_bet(
        outcome=market.outcomes[0],
        amount=USD(1),  # Polymarket minimum
    )

    assert tx_hash is not None
    assert tx_hash.startswith("0x")
    assert len(tx_hash) > 2
