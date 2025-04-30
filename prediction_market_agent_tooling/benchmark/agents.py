import random
import typing as t

from prediction_market_agent_tooling.benchmark.utils import (
    OutcomePrediction,
    Prediction,
)
from prediction_market_agent_tooling.tools.utils import DatetimeUTC


class AbstractBenchmarkedAgent:
    def __init__(
        self,
        agent_name: str,
        max_workers: t.Optional[int] = None,
        model: str | None = None,
    ):
        self.model = model
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
        time_restriction_up_to: DatetimeUTC,
    ) -> bool:
        """
        Override if the agent can decide to not predict the question, before doing the hard work.

        Data used for the evaluation must be restricted to the time_restriction_up_to.
        """
        return True

    def predict_restricted(
        self,
        market_question: str,
        time_restriction_up_to: DatetimeUTC,
    ) -> Prediction:
        """
        Predict the outcome of the market question.

        Data used for the prediction must be restricted to the time_restriction_up_to.
        """
        raise NotImplementedError

    def check_and_predict_restricted(
        self,
        market_question: str,
        time_restriction_up_to: DatetimeUTC,
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
        confidence = random.random()
        return Prediction(
            outcome_prediction=OutcomePrediction(
                confidence=confidence,
                info_utility=None,
                probabilities={},
            ),
        )

    def predict_restricted(
        self, market_question: str, time_restriction_up_to: DatetimeUTC
    ) -> Prediction:
        return self.predict(market_question)


class FixedAgent(AbstractBenchmarkedAgent):
    def __init__(
        self, fixed_answer_idx: int, agent_name: str, max_workers: int | None = None
    ):
        super().__init__(agent_name, max_workers)
        self.fixed_answer_idx = fixed_answer_idx

    def predict(self, market_question: str) -> Prediction:
        p_yes, confidence = 1.0 if self.fixed_answer_idx else 0.0, 1.0
        # We simply select a fixed probability for the first outcome.
        return Prediction(
            outcome_prediction=OutcomePrediction(
                probabilities={},
                confidence=confidence,
                info_utility=None,
            ),
        )

    def predict_restricted(
        self, market_question: str, time_restriction_up_to: DatetimeUTC
    ) -> Prediction:
        return self.predict(market_question)
