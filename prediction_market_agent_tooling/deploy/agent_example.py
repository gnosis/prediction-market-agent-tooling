import random

from prediction_market_agent_tooling.deploy.agent import (
    DeployableTraderAgent,
    ProbabilisticAnswer,
)
from prediction_market_agent_tooling.gtypes import Probability
from prediction_market_agent_tooling.markets.agent_market import AgentMarket
from prediction_market_agent_tooling.markets.markets import MarketType


class DeployableCoinFlipAgent(DeployableTraderAgent):
    def verify_market(self, market_type: MarketType, market: AgentMarket) -> bool:
        return True

    def answer_binary_market(self, market: AgentMarket) -> ProbabilisticAnswer | None:
        decision = random.choice([True, False])
        return ProbabilisticAnswer(
            p_yes=Probability(float(decision)),
            confidence=0.5,
            reasoning="I flipped a coin to decide.",
        )


class DeployableAlwaysRaiseAgent(DeployableTraderAgent):
    def answer_binary_market(self, market: AgentMarket) -> ProbabilisticAnswer | None:
        raise RuntimeError("I always raise!")
