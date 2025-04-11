import random

from prediction_market_agent_tooling.config import APIKeys
from prediction_market_agent_tooling.deploy.agent import (
    DeployableTraderAgent,
    ProbabilisticAnswer,
)
from prediction_market_agent_tooling.deploy.betting_strategy import (
    BettingStrategy,
    MultiCategoricalMaxAccuracyBettingStrategy,
)
from prediction_market_agent_tooling.gtypes import Probability
from prediction_market_agent_tooling.markets.agent_market import AgentMarket, SortBy
from prediction_market_agent_tooling.markets.markets import MarketType


class DeployableCoinFlipAgent(DeployableTraderAgent):
    fetch_categorical_markets = True
    get_markets_sort_by = SortBy.HIGHEST_LIQUIDITY

    def get_betting_strategy(self, market: AgentMarket) -> BettingStrategy:
        """
        Override this method to customize betting strategy of your agent.

        Given the market and prediction, agent uses this method to calculate optimal outcome and bet size.
        """
        user_id = market.get_user_id(api_keys=APIKeys())

        total_amount = market.get_in_usd(market.get_tiny_bet_amount())
        if existing_position := market.get_position(user_id=user_id):
            total_amount += existing_position.total_amount_current

        return MultiCategoricalMaxAccuracyBettingStrategy(bet_amount=total_amount)

    def verify_market(self, market_type: MarketType, market: AgentMarket) -> bool:
        return True

    def answer_binary_market(self, market: AgentMarket) -> ProbabilisticAnswer | None:
        # decision = random.choice([True, False])
        decision = random.choice(market.outcomes)
        probabilities_multi = {decision: Probability(1.0)}
        for outcome in market.outcomes:
            if outcome != decision:
                probabilities_multi[outcome] = Probability(0.0)
        return ProbabilisticAnswer(
            # p_yes=Probability(float(decision)),
            probabilities_multi=probabilities_multi,
            confidence=0.5,
            reasoning="I flipped a coin to decide.",
        )


class DeployableAlwaysRaiseAgent(DeployableTraderAgent):
    def answer_binary_market(self, market: AgentMarket) -> ProbabilisticAnswer | None:
        raise RuntimeError("I always raise!")
