from collections import defaultdict

from prediction_market_agent_tooling.gtypes import HexBytes
from prediction_market_agent_tooling.markets.seer.data_models import SeerMarketQuestions
from prediction_market_agent_tooling.markets.seer.seer_subgraph_handler import (
    SeerSubgraphHandler,
)
from prediction_market_agent_tooling.tools.singleton import SingletonMeta


class SeerQuestionsCache(metaclass=SingletonMeta):
    """A singleton cache for storing and retrieving Seer market questions.

    This class provides an in-memory cache for Seer market questions, preventing
    redundant subgraph queries by maintaining a mapping of market IDs to their
    associated questions. It implements the singleton pattern to ensure a single
    cache instance is used throughout the agent run.

    Attributes:
        market_id_to_questions: A dictionary mapping market IDs to lists of SeerMarketQuestions
        seer_subgraph_handler: Handler for interacting with the Seer subgraph
    """

    def __init__(self, seer_subgraph_handler: SeerSubgraphHandler | None = None):
        self.market_id_to_questions: dict[
            HexBytes, list[SeerMarketQuestions]
        ] = defaultdict(list)
        self.seer_subgraph_handler = seer_subgraph_handler or SeerSubgraphHandler()

    def fetch_questions(self, market_ids: list[HexBytes]) -> list[SeerMarketQuestions]:
        filtered_list = [
            market_id
            for market_id in market_ids
            if market_id not in self.market_id_to_questions
        ]

        questions = self.seer_subgraph_handler.get_questions_for_markets(filtered_list)
        # Group questions by market_id
        questions_by_market: dict[HexBytes, list[SeerMarketQuestions]] = defaultdict(
            list
        )
        for q in questions:
            questions_by_market[q.market.id].append(q)

        # Update the cache with the new questions for each market
        for market_id, market_questions in questions_by_market.items():
            self.market_id_to_questions[market_id] = market_questions

        return questions
