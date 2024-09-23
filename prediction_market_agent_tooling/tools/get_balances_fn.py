from typing import Callable

from prediction_market_agent_tooling.config import APIKeys
from prediction_market_agent_tooling.markets.markets import MarketType
from prediction_market_agent_tooling.tools.balances import get_balances


def get_balance_fn(market_type: MarketType) -> Callable[[], float]:
    if market_type == MarketType.OMEN:
        keys = APIKeys()

        def balance_fn() -> float:
            return float(get_balances(keys.bet_from_address).total)

        return balance_fn
    else:
        raise ValueError(f"Unsupported market type: {market_type}")
