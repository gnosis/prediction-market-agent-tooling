import random

from prediction_market_agent_tooling.deploy.agent import (
    DeployableTraderAgent,
    ProbabilisticAnswer,
)
from prediction_market_agent_tooling.gtypes import Probability
from prediction_market_agent_tooling.loggers import logger
from prediction_market_agent_tooling.markets.agent_market import (
    AgentMarket,
    ProcessedTradedMarket,
    ProcessedMarket,
)
from prediction_market_agent_tooling.markets.markets import MarketType


class DeployableCoinFlipAgent(DeployableTraderAgent):
    def verify_market(self, market_type: MarketType, market: AgentMarket) -> bool:
        return True

    def pre_process_market(
        self,
        market_type: MarketType,
        market: AgentMarket,
        verify_market: bool = True,
    ):
        self.update_langfuse_trace_by_market(market_type, market)
        logger.info(
            f"Processing market {market.question=} from {market.url=} with liquidity {market.get_liquidity()}."
        )

        answer: ProbabilisticAnswer | None
        if verify_market and not self.verify_market(market_type, market):
            logger.info(f"Market '{market.question}' doesn't meet the criteria.")
            answer = None
        else:
            logger.info(f"Answering market '{market.question}'.")
            answer = self.answer_binary_market(market)

        processed_market = (
            ProcessedMarket(answer=answer) if answer is not None else None
        )

        self.update_langfuse_trace_by_processed_market(market_type, processed_market)
        logger.info(
            f"Processed market {market.question=} from {market.url=} with {answer=}."
        )
        return processed_market

    def process_market(
        self,
        market_type: MarketType,
        market: AgentMarket,
        verify_market: bool = True,
    ) -> ProcessedTradedMarket | None:
        # ToDo - add methods for multi
        processed_market = self.pre_process_market(
            market_type=market_type, market=market, verify_market=verify_market
        )

        if processed_market is None:
            return None
        # ToDo:
        #  create trades
        #  place trades
        return None

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


class DeployableCategoricalCoinFlipAgent(DeployableTraderAgent):
    def verify_market(self, market_type: MarketType, market: AgentMarket) -> bool:
        return True

    # ToDo - Add categorical methods

    def answer_binary_market(self, market: AgentMarket) -> ProbabilisticAnswer | None:
        decision = random.choice([True, False])
        return ProbabilisticAnswer(
            p_yes=Probability(float(decision)),
            confidence=0.5,
            reasoning="I flipped a coin to decide.",
        )
