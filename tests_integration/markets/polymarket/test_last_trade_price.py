import pytest

from prediction_market_agent_tooling.markets.polymarket.api import (
    get_last_trade_price_from_clob,
)

# Token ID for "Yes" on an active, high-volume Polymarket market.
# 2024 US Presidential Election — "Will a Republican win?" Yes token.
KNOWN_ACTIVE_TOKEN_ID = 21742633143463906290569050155826241533067272736897614950488156847949938836455


@pytest.mark.parametrize("token_id", [KNOWN_ACTIVE_TOKEN_ID])
def test_last_trade_price_returns_valid_float(token_id: int) -> None:
    price = get_last_trade_price_from_clob(token_id)
    assert price is not None, "Expected a price for an active token"
    assert 0 <= price <= 1, f"Price {price} outside expected [0, 1] range"
