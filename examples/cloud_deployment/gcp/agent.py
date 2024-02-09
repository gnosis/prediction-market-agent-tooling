from flask.wrappers import Request
import functions_framework
import random

from prediction_market_agent_tooling.markets.data_models import AgentMarket
from prediction_market_agent_tooling.deploy.agent import DeployableAgent
from prediction_market_agent_tooling.markets.markets import MarketType
from prediction_market_agent_tooling.config import APIKeys


class DeployableCoinFlipAgent(DeployableAgent):
    def pick_markets(self, markets: list[AgentMarket]) -> list[AgentMarket]:
        if len(markets) > 1:
            return random.sample(markets, 1)
        return markets

    def answer_binary_market(self, market: AgentMarket) -> bool:
        return random.choice([True, False])


@functions_framework.http
def main(request: Request) -> str:
    DeployableCoinFlipAgent().run(market_type=MarketType.MANIFOLD, api_keys=APIKeys())
    return "Success"
