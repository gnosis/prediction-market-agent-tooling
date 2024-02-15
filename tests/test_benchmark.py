import tempfile

import pytest

import prediction_market_agent_tooling.benchmark.benchmark as bm
from prediction_market_agent_tooling.benchmark.utils import (
    EvaluatedQuestion,
    MarketSource,
    OutcomePrediction,
    get_markets,
)


class DummyAgent(bm.AbstractBenchmarkedAgent):
    def __init__(self) -> None:
        super().__init__(agent_name="dummy")

    def evaluate_research_predict(self, market_question: str) -> bm.Prediction:
        return bm.Prediction(
            evaluation=EvaluatedQuestion(
                question=market_question,
                is_predictable=True,
            ),
            outcome_prediction=OutcomePrediction(
                p_yes=0.6,
                confidence=0.8,
                info_utility=0.9,
            ),
        )


@pytest.fixture
def dummy_agent() -> DummyAgent:
    return DummyAgent()


class DummyAgentNoPrediction(bm.AbstractBenchmarkedAgent):
    def __init__(self) -> None:
        super().__init__(agent_name="dummy_no_prediction")

    def evaluate_research_predict(self, market_question: str) -> bm.Prediction:
        return bm.Prediction(
            evaluation=EvaluatedQuestion(
                question=market_question,
                is_predictable=False,
            ),
            outcome_prediction=None,
        )


@pytest.fixture
def dummy_agent_no_prediction() -> DummyAgentNoPrediction:
    return DummyAgentNoPrediction()


def test_agent_prediction(dummy_agent: DummyAgent) -> None:
    prediction = dummy_agent.evaluate_research_predict(
        market_question="Will GNO go up?"
    )
    assert prediction.outcome_prediction is not None
    assert prediction.outcome_prediction.p_yes == 0.6
    assert prediction.outcome_prediction.confidence == 0.8
    assert prediction.outcome_prediction.info_utility == 0.9


def test_benchmark_run(
    dummy_agent: DummyAgent, dummy_agent_no_prediction: DummyAgentNoPrediction
) -> None:
    benchmarker = bm.Benchmarker(
        markets=get_markets(number=1, source=MarketSource.MANIFOLD),
        agents=[dummy_agent, dummy_agent_no_prediction],
    )
    benchmarker.run_agents()
    benchmarker.generate_markdown_report()


def test_cache() -> None:
    cache = bm.PredictionsCache(
        predictions={
            "bar": {
                "foo": bm.Prediction(
                    outcome_prediction=OutcomePrediction(
                        p_yes=0.6, confidence=0.8, info_utility=0.9
                    )
                )
            }
        }
    )

    with tempfile.TemporaryDirectory() as tmpdir:
        cache_path = f"{tmpdir}/cache.json"
        cache.save(cache_path)

        cache_loaded = bm.PredictionsCache.parse_file(cache_path)
        assert cache == cache_loaded


def test_benchmarker_cache(dummy_agent: DummyAgent) -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        cache_path = f"{tmpdir}/cache.json"
        markets = get_markets(number=1, source=MarketSource.MANIFOLD)
        benchmarker = bm.Benchmarker(
            markets=markets,
            agents=[dummy_agent],
            cache_path=cache_path,
        )
        prediction = bm.Prediction(
            outcome_prediction=OutcomePrediction(
                info_utility=0.3333,
                p_yes=0.00001,
                confidence=0.22222,
            ),
        )
        assert prediction.outcome_prediction is not None  # Makes mypy happy.
        benchmarker.add_prediction(
            agent=dummy_agent,
            prediction=prediction,
            market_question=markets[0].question,
        )
        first_benchmark_prediction = benchmarker.get_prediction(
            agent_name=dummy_agent.agent_name, question=markets[0].question
        )
        assert first_benchmark_prediction is not None
        assert first_benchmark_prediction.outcome_prediction is not None
        assert (
            first_benchmark_prediction.outcome_prediction.p_yes
            == prediction.outcome_prediction.p_yes
        )
        benchmarker.predictions.save(cache_path)

        another_benchmarker = bm.Benchmarker(
            markets=markets,
            agents=[dummy_agent],
            cache_path=cache_path,
        )
        another_benchmark_prediction = another_benchmarker.get_prediction(
            agent_name=dummy_agent.agent_name, question=markets[0].question
        )
        assert another_benchmark_prediction is not None
        assert another_benchmark_prediction.outcome_prediction is not None
        assert (
            another_benchmark_prediction.outcome_prediction.p_yes
            == prediction.outcome_prediction.p_yes
        )
        another_benchmarker.run_agents()

        # Observe that the cached result is still the same
        assert (
            another_benchmark_prediction.outcome_prediction.p_yes
            == prediction.outcome_prediction.p_yes
        )
