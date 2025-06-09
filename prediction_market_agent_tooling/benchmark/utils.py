import json
import typing as t

from pydantic import BaseModel

from prediction_market_agent_tooling.gtypes import OutcomeStr, Probability
from prediction_market_agent_tooling.markets.data_models import (
    CategoricalProbabilisticAnswer,
)


def get_most_probable_outcome(
    probability_map: dict[OutcomeStr, Probability],
) -> OutcomeStr:
    """Returns most probable outcome. If tied, returns first."""
    return max(probability_map, key=lambda k: float(probability_map[k]))


class Prediction(BaseModel):
    is_predictable: bool = True
    outcome_prediction: t.Optional[CategoricalProbabilisticAnswer] = None

    time: t.Optional[float] = None
    cost: t.Optional[float] = None

    @property
    def is_answered(self) -> bool:
        return self.outcome_prediction is not None


AgentPredictions = t.Dict[str, Prediction]
Predictions = t.Dict[str, AgentPredictions]


class PredictionsCache(BaseModel):
    predictions: Predictions

    def get_prediction(self, agent_name: str, question: str) -> Prediction:
        return self.predictions[agent_name][question]

    def has_market(self, agent_name: str, question: str) -> bool:
        return (
            agent_name in self.predictions and question in self.predictions[agent_name]
        )

    def add_prediction(
        self, agent_name: str, question: str, prediction: Prediction
    ) -> None:
        if agent_name not in self.predictions:
            self.predictions[agent_name] = {}
        assert (
            question not in self.predictions[agent_name]
        ), f"Question `{question}` already exists in the cache."
        self.predictions[agent_name][question] = prediction

    def save(self, path: str) -> None:
        with open(path, "w") as f:
            json.dump(self.model_dump(), f, indent=2)

    @staticmethod
    def load(path: str) -> "PredictionsCache":
        with open(path, "r") as f:
            return PredictionsCache.model_validate(json.load(f))


def get_llm_api_call_cost(
    model: str, prompt_tokens: int, completion_tokens: float
) -> float:
    """
    In older versions of langchain, the cost calculation doesn't work for
    newer models. This is a temporary workaround to get the cost.

    See:
    https://github.com/langchain-ai/langchain/issues/12994

    Costs are in USD, per 1000 tokens.
    """
    model_costs = {
        "gpt-4-1106-preview": {
            "prompt_tokens": 0.01,
            "completion_tokens": 0.03,
        },
        "gpt-4-turbo-2024-04-09": {
            "prompt_tokens": 0.01,
            "completion_tokens": 0.03,
        },
        "gpt-3.5-turbo-0125": {
            "prompt_tokens": 0.0005,
            "completion_tokens": 0.0015,
        },
    }
    if model not in model_costs:
        raise ValueError(f"Unknown model: {model}")

    model_cost = model_costs[model]["prompt_tokens"] * prompt_tokens
    model_cost += model_costs[model]["completion_tokens"] * completion_tokens
    model_cost /= 1000
    return model_cost
