import random
import typing as t

from prediction_market_agent_tooling.deploy.agent import (
    Answer,
    DeployableTraderAgent,
    Probability,
)
from prediction_market_agent_tooling.markets.agent_market import AgentMarket
from prediction_market_agent_tooling.markets.markets import MarketType


class DeployableCoinFlipAgent(DeployableTraderAgent):
    def pick_markets(
        self, market_type: MarketType, markets: t.Sequence[AgentMarket]
    ) -> t.Sequence[AgentMarket]:
        return random.sample(markets, 1)

    def answer_binary_market(self, market: AgentMarket) -> Answer | None:
        decision = random.choice([True, False])
        return Answer(
            decision=decision,
            p_yes=Probability(float(decision)),
            confidence=0.5,
            reasoning="I flipped a coin to decide.",
        )


class DeployableAlwaysRaiseAgent(DeployableTraderAgent):
    def answer_binary_market(self, market: AgentMarket) -> Answer | None:
        raise RuntimeError("I always raise!")
