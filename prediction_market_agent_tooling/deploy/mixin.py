from prediction_market_agent_tooling.gtypes import USD
from prediction_market_agent_tooling.markets.agent_market import AgentMarket


class FixedBettingMixin:
    def get_total_amount_to_bet(self, market: AgentMarket) -> USD:
        """Always bet fixed amounts, regardless of the agent's open interest."""
        return market.get_in_usd(market.get_tiny_bet_amount())
