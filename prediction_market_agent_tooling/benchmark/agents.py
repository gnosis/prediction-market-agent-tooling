import random
import typing as t
from datetime import datetime

from prediction_market_agent_tooling.benchmark.utils import (
    OutcomePrediction,
    Prediction,
)


class AbstractBenchmarkedAgent:
    def __init__(self, agent_name: str, max_workers: t.Optional[int] = None):
        self.agent_name = agent_name
        self.max_workers = max_workers  # Limit the number of workers that can run this worker in parallel threads

    def is_predictable(self, market_question: str) -> bool:
        """
        Override if the agent can decide to not predict the question, before doing the hard work.
        """
        return True

    def predict(self, market_question: str) -> Prediction:
        """
        Predict the outcome of the market question.
        """
        raise NotImplementedError

    def check_and_predict(self, market_question: str) -> Prediction:
        is_predictable = self.is_predictable(market_question=market_question)
        if not is_predictable:
            return Prediction(is_predictable=is_predictable)
        return self.predict(market_question=market_question)

    def is_predictable_restricted(
        self,
        market_question: str,
        time_restriction_up_to: datetime,
    ) -> bool:
        """
        Override if the agent can decide to not predict the question, before doing the hard work.

        Data used for the evaluation must be restricted to the time_restriction_up_to.
        """
        return True

    def predict_restricted(
        self,
        market_question: str,
        time_restriction_up_to: datetime,
    ) -> Prediction:
        """
        Predict the outcome of the market question.

        Data used for the prediction must be restricted to the time_restriction_up_to.
        """
        raise NotImplementedError

    def check_and_predict_restricted(
        self,
        market_question: str,
        time_restriction_up_to: datetime,
    ) -> Prediction:
        """
        Data used must be restricted to the time_restriction_up_to.
        """
        is_predictable = self.is_predictable_restricted(
            market_question=market_question,
            time_restriction_up_to=time_restriction_up_to,
        )
        if not is_predictable:
            return Prediction(is_predictable=is_predictable)
        return self.predict_restricted(
            market_question=market_question,
            time_restriction_up_to=time_restriction_up_to,
        )


class RandomAgent(AbstractBenchmarkedAgent):
    def predict(self, market_question: str) -> Prediction:
        p_yes, confidence = random.random(), random.random()
        return Prediction(
            outcome_prediction=OutcomePrediction(
                p_yes=p_yes,
                confidence=confidence,
                info_utility=None,
            ),
        )

    def predict_restricted(
        self, market_question: str, time_restriction_up_to: datetime
    ) -> Prediction:
        return self.predict(market_question)


class FixedAgent(AbstractBenchmarkedAgent):
    def __init__(
        self, fixed_answer: bool, agent_name: str, max_workers: int | None = None
    ):
        super().__init__(agent_name, max_workers)
        self.fixed_answer = fixed_answer

    def predict(self, market_question: str) -> Prediction:
        p_yes, confidence = 1.0 if self.fixed_answer else 0.0, 1.0
        return Prediction(
            outcome_prediction=OutcomePrediction(
                p_yes=p_yes,
                confidence=confidence,
                info_utility=None,
            ),
        )

    def predict_restricted(
        self, market_question: str, time_restriction_up_to: datetime
    ) -> Prediction:
        return self.predict(market_question)
