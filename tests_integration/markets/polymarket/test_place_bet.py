import pytest

from prediction_market_agent_tooling.config import APIKeys
from prediction_market_agent_tooling.gtypes import USD, OutcomeToken
from prediction_market_agent_tooling.markets.polymarket.api import get_user_trades
from prediction_market_agent_tooling.markets.polymarket.data_models import (
    PolymarketSideEnum,
)
from prediction_market_agent_tooling.markets.polymarket.polymarket import (
    PolymarketAgentMarket,
)
from tests.utils import RUN_PAID_TESTS


@pytest.mark.skipif(not RUN_PAID_TESTS, reason="This test costs money to run.")
def test_place_and_sell_bet_real() -> None:
    """Place a real $1 bet on Polymarket, then sell the position.

    Requires RUN_PAID_TESTS=1 and BET_FROM_PRIVATE_KEY with USDC on Polygon.
    Validates the full buy -> verify trade -> sell -> verify no position cycle.
    """
    api_keys = APIKeys()
    user_address = api_keys.bet_from_address

    trades_before = get_user_trades(user_address=user_address)

    markets = PolymarketAgentMarket.get_markets(limit=5)
    market = next(m for m in markets if m.can_be_traded())
    outcome = market.outcomes[0]

    # --- BUY ---
    buy_tx = market.place_bet(
        outcome=outcome,
        amount=USD(1),  # Polymarket minimum
    )

    assert buy_tx is not None
    assert buy_tx.startswith("0x")

    # Verify the buy trade shows up in the Data API
    trades_after_buy = get_user_trades(user_address=user_address)
    assert len(trades_after_buy) > len(trades_before), (
        f"Expected more trades after buy, "
        f"got {len(trades_after_buy)} (before: {len(trades_before)})"
    )
    buy_trade = trades_after_buy[0]
    assert buy_trade.conditionId == market.condition_id
    assert buy_trade.side == PolymarketSideEnum.BUY

    # --- SELL ---
    position_before_sell = market.get_position(user_id=user_address)
    assert position_before_sell is not None
    tokens_held = position_before_sell.amounts_ot[outcome]
    assert tokens_held > OutcomeToken(0), "Expected tokens to sell"

    sell_tx = market.sell_tokens(
        outcome=outcome,
        amount=tokens_held,
        api_keys=api_keys,
    )

    assert sell_tx is not None
    assert sell_tx.startswith("0x")

    # Verify the sell trade shows up
    trades_after_sell = get_user_trades(user_address=user_address)
    assert len(trades_after_sell) > len(trades_after_buy)
    sell_trade = trades_after_sell[0]
    assert sell_trade.conditionId == market.condition_id
    assert sell_trade.side == PolymarketSideEnum.SELL

    # Verify position is gone or zero
    position_after_sell = market.get_position(user_id=user_address)
    if position_after_sell is not None:
        assert position_after_sell.amounts_ot[outcome] == OutcomeToken(0)
