from abc import ABC, abstractmethod
from datetime import timedelta

from prediction_market_agent_tooling.markets.agent_market import AgentMarket


class TradeInterval(ABC):
    @abstractmethod
    def get(
        self,
        market: AgentMarket,
    ) -> timedelta:
        raise NotImplementedError("Subclass should implement this.")


class FixedInterval(TradeInterval):
    """
    For trades at a fixed interval.
    """

    def __init__(self, interval: timedelta):
        self.interval = interval

    def get(
        self,
        market: AgentMarket,
    ) -> timedelta:
        return self.interval


class MarketLifetimeProportionalInterval(TradeInterval):
    """
    For uniformly distributed trades over the market's lifetime.
    """

    def __init__(self, max_trades: int):
        self.max_trades = max_trades

    def get(
        self,
        market: AgentMarket,
    ) -> timedelta:
        return (market.close_time - market.created_time) / self.max_trades
