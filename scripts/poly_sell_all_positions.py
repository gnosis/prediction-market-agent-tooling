from prediction_market_agent_tooling.markets.polymarket.polymarket import (
    PolymarketAgentMarket,
)


def main() -> None:
    PolymarketAgentMarket.sell_all_user_positions()


if __name__ == "__main__":
    main()
