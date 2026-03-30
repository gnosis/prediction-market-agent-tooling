from prediction_market_agent_tooling.markets.polymarket.polymarket import (
    PolymarketAgentMarket,
)


def test_active_market_can_be_traded() -> None:
    markets = PolymarketAgentMarket.get_markets(limit=1)
    assert len(markets) > 0, "No open markets found on Polymarket"
    market = markets[0]
    assert market.can_be_traded(), (
        f"Expected active market to be tradeable: "
        f"active={market.active_flag_from_polymarket}, "
        f"closed={market.closed_flag_from_polymarket}, "
        f"liquidity={market.liquidity_usd}"
    )
