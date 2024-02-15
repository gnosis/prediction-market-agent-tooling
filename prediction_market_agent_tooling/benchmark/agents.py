import random
import typing as t

from prediction_market_agent_tooling.benchmark.utils import (
    EvaluatedQuestion,
    OutcomePrediction,
    Prediction,
)


class AbstractBenchmarkedAgent:
    def __init__(self, agent_name: str, max_workers: t.Optional[int] = None):
        self.agent_name = agent_name
        self.max_workers = max_workers  # Limit the number of workers that can run this worker in parallel threads

    def evaluate(self, market_question: str) -> EvaluatedQuestion:
        raise NotImplementedError

    def research(self, market_question: str) -> t.Optional[str]:
        raise NotImplementedError

    def predict(
        self, market_question: str, researched: str, evaluated: EvaluatedQuestion
    ) -> Prediction:
        raise NotImplementedError

    def evaluate_research_predict(self, market_question: str) -> Prediction:
        eval = self.evaluate(market_question=market_question)
        if not eval.is_predictable:
            return Prediction(evaluation=eval)
        researched = self.research(market_question=market_question)
        if researched is None:
            return Prediction(evaluation=eval)
        return self.predict(
            market_question=market_question,
            researched=researched,
            evaluated=eval,
        )


class RandomAgent(AbstractBenchmarkedAgent):
    def evaluate(self, market_question: str) -> EvaluatedQuestion:
        return EvaluatedQuestion(question=market_question, is_predictable=True)

    def research(self, market_question: str) -> str:
        return ""  # No research for a random agent, but can't be None.

    def predict(
        self, market_question: str, researched: str, evaluated: EvaluatedQuestion
    ) -> Prediction:
        p_yes, confidence = random.random(), random.random()
        return Prediction(
            evaluation=evaluated,
            outcome_prediction=OutcomePrediction(
                p_yes=p_yes,
                confidence=confidence,
                info_utility=None,
            ),
        )


class FixedAgent(AbstractBenchmarkedAgent):
    def __init__(
        self, fixed_answer: bool, agent_name: str, max_workers: int | None = None
    ):
        super().__init__(agent_name, max_workers)
        self.fixed_answer = fixed_answer

    def evaluate(self, market_question: str) -> EvaluatedQuestion:
        return EvaluatedQuestion(question=market_question, is_predictable=True)

    def research(self, market_question: str) -> str:
        return ""  # No research for a fixed agent, but can't be None.

    def predict(
        self, market_question: str, researched: str, evaluated: EvaluatedQuestion
    ) -> Prediction:
        p_yes, confidence = 1.0 if self.fixed_answer else 0.0, 1.0
        return Prediction(
            evaluation=evaluated,
            outcome_prediction=OutcomePrediction(
                p_yes=p_yes,
                confidence=confidence,
                info_utility=None,
            ),
        )
