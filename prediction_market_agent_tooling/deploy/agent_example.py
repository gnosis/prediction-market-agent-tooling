import random

from prediction_market_agent_tooling.deploy.agent import DeployableTraderAgent
from prediction_market_agent_tooling.markets.data_models import (
    CategoricalProbabilisticAnswer,
)
from prediction_market_agent_tooling.gtypes import Probability
from prediction_market_agent_tooling.markets.agent_market import AgentMarket, SortBy
from prediction_market_agent_tooling.markets.markets import MarketType


class DeployableCoinFlipAgent(DeployableTraderAgent):
    fetch_categorical_markets = True
    get_markets_sort_by = SortBy.HIGHEST_LIQUIDITY

    def verify_market(self, market_type: MarketType, market: AgentMarket) -> bool:
        return True

    def answer_categorical_market(
        self, market: AgentMarket
    ) -> CategoricalProbabilisticAnswer:
        decision = random.choice(market.outcomes)
        probabilities = {decision: Probability(1.0)}
        for outcome in market.outcomes:
            if outcome != decision:
                probabilities[outcome] = Probability(0.0)
        return CategoricalProbabilisticAnswer(
            probabilities=probabilities,
            confidence=0.5,
            reasoning="I flipped a coin to decide.",
        )


class DeployableAlwaysRaiseAgent(DeployableTraderAgent):
    def answer_categorical_market(
        self, market: AgentMarket
    ) -> CategoricalProbabilisticAnswer | None:
        raise RuntimeError("I always raise!")
