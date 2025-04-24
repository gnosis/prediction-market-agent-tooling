import random
import typing as t

from prediction_market_agent_tooling.deploy.agent import (
    DeployableTraderAgent,
    ProbabilisticAnswer,
    DeployableAgent,
)
from prediction_market_agent_tooling.gtypes import Probability, OutcomeStr
from prediction_market_agent_tooling.loggers import logger
from prediction_market_agent_tooling.markets.agent_market import (
    AgentMarket,
    ProcessedTradedMarket,
    SortBy,
    FilterBy,
)
from prediction_market_agent_tooling.markets.data_models import MultiProbabilisticAnswer
from prediction_market_agent_tooling.markets.markets import MarketType
from prediction_market_agent_tooling.markets.seer.seer import SeerAgentMarket
from prediction_market_agent_tooling.tools.datetime_utc import DatetimeUTC


class DeployableCoinFlipAgent(DeployableAgent):
    bet_on_n_markets_per_run: int = 1
    n_markets_to_fetch: int = 5
    trade_on_markets_created_after: DatetimeUTC | None = None
    get_markets_sort_by: SortBy = SortBy.HIGHEST_LIQUIDITY

    def verify_market(self, market_type: MarketType, market: AgentMarket) -> bool:
        return True

    def run(self, market_type: MarketType) -> None:
        self.process_markets(market_type)

    def get_markets(
        self,
    ) -> t.Sequence[AgentMarket]:
        # Fetch the soonest closing markets to choose from
        available_markets = SeerAgentMarket.get_categorical_markets(
            limit=self.n_markets_to_fetch,
            sort_by=self.get_markets_sort_by,
            filter_by=FilterBy.OPEN,
        )
        return available_markets

    def process_markets(self, market_type: MarketType) -> None:
        available_markets = self.get_markets()
        processed = 0
        for market_idx, market in enumerate(available_markets):
            logger.info(
                f"Going to process market {market.url}: {market_idx + 1} / {len(available_markets)}."
            )

            processed_market = self.process_market(market_type, market)

            if processed_market is not None:
                processed += 1

            if processed == self.bet_on_n_markets_per_run:
                break

        logger.info(
            f"All markets processed. Successfully processed {processed}/{len(available_markets)}."
        )

    def process_market(
        self,
        market_type: MarketType,
        market: AgentMarket,
        verify_market: bool = True,
    ) -> ProcessedTradedMarket | None:
        # ToDo
        #  trades
        logger.info(
            f"Processing market {market.question=} from {market.url=} with liquidity {market.get_liquidity()}."
        )
        # ToDo - Can we unify the types here with DeployableTraderAgent?
        answer: MultiProbabilisticAnswer | None
        if verify_market and not self.verify_market(market_type, market):
            logger.info(f"Market '{market.question}' doesn't meet the criteria.")
            answer = None
        else:
            logger.info(f"Answering market '{market.question}'.")
            answer = self.answer_categorical_market(market)

        # ToDo - add trades
        processed_market = (
            ProcessedTradedMarket(answer=answer, trades=[])
            if answer is not None
            else None
        )

        return processed_market

    def answer_categorical_market(
        self, market: AgentMarket
    ) -> MultiProbabilisticAnswer | None:
        outcome = random.choice(market.outcomes)
        probs = {OutcomeStr(outcome): Probability(0.0) for outcome in market.outcomes}
        probs[OutcomeStr(outcome)] = Probability(1.0)

        return MultiProbabilisticAnswer(
            probabilities_multi=probs,
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
