from prediction_market_agent_tooling.markets.polymarket.api import (
    get_polymarket_binary_markets,
    get_polymarket_market,
)
from prediction_market_agent_tooling.markets.polymarket.polymarket import (
    PolymarketAgentMarket,
)


def test_get_single_odd_market():
    # https://polymarket.com/event/presidential-election-winner-2024?tid=1750841800445
    # ToDo - find condition_id from full_market
    condition_id = "1750841800445"
    market = get_polymarket_market(condition_id=condition_id)
    print(f"{market=}")
    print("done")


def test_get_markets():
    markets = get_polymarket_binary_markets(
        limit=10,
        closed=False,
    )

    assert len(markets) > 0
    for m in markets:
        # ToDo - should we also check category?
        agent_market = PolymarketAgentMarket.from_data_model(m)
        assert all(
            [
                j is not None
                for j in [
                    agent_market.question,
                    agent_market.close_time,
                    agent_market.description,
                    agent_market.url,
                ]
            ]
        )
