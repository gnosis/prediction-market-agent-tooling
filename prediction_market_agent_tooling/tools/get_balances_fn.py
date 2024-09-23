from typing import Callable

from prediction_market_agent_tooling.config import APIKeys
from prediction_market_agent_tooling.markets.markets import MarketType
from prediction_market_agent_tooling.tools.balances import get_balances


def get_balance(market_type: MarketType) -> float:
    keys = APIKeys()
    if market_type == MarketType.OMEN:
        return float(get_balances(keys.bet_from_address).total)
    raise ValueError(f"Unsupported market type: {market_type}")


def get_balance_fn(market_type: MarketType) -> Callable[[], float]:
    return lambda: get_balance(market_type)
