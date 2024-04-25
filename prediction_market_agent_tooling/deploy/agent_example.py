import random
import typing as t

from prediction_market_agent_tooling.deploy.agent import (
    Answer,
    DeployableAgent,
    Probability,
)
from prediction_market_agent_tooling.markets.agent_market import AgentMarket


class DeployableCoinFlipAgent(DeployableAgent):
    def pick_markets(self, markets: t.Sequence[AgentMarket]) -> t.Sequence[AgentMarket]:
        return random.sample(markets, 1)

    def answer_binary_market(self, market: AgentMarket) -> Answer | None:
        decision = random.choice([True, False])
        return Answer(
            decision=decision,
            p_yes=Probability(float(decision)),
            confidence=0.5,
            reasoning="I flipped a coin to decide.",
        )


class DeployableAlwaysRaiseAgent(DeployableAgent):
    def answer_binary_market(self, market: AgentMarket) -> Answer | None:
        raise RuntimeError("I always raise!")
