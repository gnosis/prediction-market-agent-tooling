import random

from prediction_market_agent_tooling.deploy.agent import (
    DeployableTraderAgent,
    ProbabilisticAnswer,
)
from prediction_market_agent_tooling.gtypes import Probability
from prediction_market_agent_tooling.markets.agent_market import AgentMarket, SortBy
from prediction_market_agent_tooling.markets.markets import MarketType


class DeployableCoinFlipAgent(DeployableTraderAgent):
    fetch_categorical_markets = True
    get_markets_sort_by = SortBy.HIGHEST_LIQUIDITY

    def verify_market(self, market_type: MarketType, market: AgentMarket) -> bool:
        return True

    def answer_binary_market(self, market: AgentMarket) -> ProbabilisticAnswer | None:
        decision = random.choice(market.outcomes)
        probabilities_multi = {decision: Probability(1.0)}
        for outcome in market.outcomes:
            if outcome != decision:
                probabilities_multi[outcome] = Probability(0.0)
        return ProbabilisticAnswer(
            probabilities_multi=probabilities_multi,
            confidence=0.5,
            reasoning="I flipped a coin to decide.",
        )


class DeployableAlwaysRaiseAgent(DeployableTraderAgent):
    def answer_binary_market(self, market: AgentMarket) -> ProbabilisticAnswer | None:
        raise RuntimeError("I always raise!")
