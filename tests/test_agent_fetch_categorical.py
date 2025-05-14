from prediction_market_agent_tooling.deploy.agent import DeployableTraderAgent
from prediction_market_agent_tooling.markets.agent_market import AgentMarket
from prediction_market_agent_tooling.markets.data_models import (
    CategoricalProbabilisticAnswer,
    ProbabilisticAnswer,
)


class ShouldFetchCategorical(DeployableTraderAgent):
    def answer_categorical_market(
        self, market: AgentMarket
    ) -> CategoricalProbabilisticAnswer:
        raise RuntimeError("I always raise!")


class ShouldNotFetchCategorical(DeployableTraderAgent):
    def answer_binary_market(self, market: AgentMarket) -> ProbabilisticAnswer:
        raise RuntimeError("I always raise!")


def test_agent_should_fetch_categorical_markets() -> None:
    assert (
        ShouldFetchCategorical().fetch_categorical_markets
    ), "Should fetch them, because `answer_categorical_market` is implemented."


def test_agent_should_not_fetch_categorical_markets() -> None:
    assert (
        not ShouldNotFetchCategorical().fetch_categorical_markets
    ), "Should not fetch them, because `answer_categorical_market` is not implemented."
