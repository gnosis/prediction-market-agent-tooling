import random
import typing as t

from prediction_market_agent_tooling.deploy.agent import DeployableAgent
from prediction_market_agent_tooling.markets.agent_market import AgentMarket


class DeployableCoinFlipAgent(DeployableAgent):
    def pick_markets(self, markets: t.Sequence[AgentMarket]) -> t.Sequence[AgentMarket]:
        return random.sample(markets, 1)

    def answer_binary_market(self, market: AgentMarket) -> bool | None:
        return random.choice([True, False])


class DeployableAlwaysRaiseAgent(DeployableAgent):
    def answer_binary_market(self, market: AgentMarket) -> bool | None:
        raise RuntimeError("I always raise!")
