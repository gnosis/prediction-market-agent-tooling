import tempfile
from datetime import timedelta

import pytest

import prediction_market_agent_tooling.benchmark.benchmark as bm
from prediction_market_agent_tooling.benchmark.utils import (
    OutcomePrediction,
    Resolution,
)
from prediction_market_agent_tooling.gtypes import OutcomeStr, Probability
from prediction_market_agent_tooling.markets.polymarket.polymarket import (
    PolymarketAgentMarket,
)
from prediction_market_agent_tooling.tools.utils import utcnow


class DummyAgent(bm.AbstractBenchmarkedAgent):
    def __init__(self) -> None:
        super().__init__(agent_name="dummy")

    def check_and_predict(self, market_question: str) -> bm.Prediction:
        return bm.Prediction(
            is_predictable=True,
            outcome_prediction=OutcomePrediction(
                p_yes=Probability(0.6),
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

    def check_and_predict(self, market_question: str) -> bm.Prediction:
        return bm.Prediction(
            is_predictable=False,
            outcome_prediction=None,
        )


@pytest.fixture
def dummy_agent_no_prediction() -> DummyAgentNoPrediction:
    return DummyAgentNoPrediction()


def test_agent_prediction(dummy_agent: DummyAgent) -> None:
    prediction = dummy_agent.check_and_predict(market_question="Will GNO go up?")
    assert prediction.outcome_prediction is not None
    assert prediction.outcome_prediction.p_yes == 0.6
    assert prediction.outcome_prediction.confidence == 0.8
    assert prediction.outcome_prediction.info_utility == 0.9


def test_benchmark_run(
    dummy_agent: DummyAgent, dummy_agent_no_prediction: DummyAgentNoPrediction
) -> None:
    benchmarker = bm.Benchmarker(
        markets=[
            PolymarketAgentMarket(
                description=None,
                id="1",
                volume=None,
                url="url",
                question="Will GNO go up?",
                outcomes=[OutcomeStr("Yes"), OutcomeStr("No")],
                close_time=utcnow() + timedelta(hours=48),
                resolution=None,
                created_time=utcnow() - timedelta(hours=48),
                outcome_token_pool=None,
            )
        ],
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
                        p_yes=Probability(0.6),
                        confidence=0.8,
                        info_utility=0.9,
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
        markets = [
            PolymarketAgentMarket(
                description=None,
                id="1",
                volume=None,
                url="url",
                question="Will GNO go up?",
                current_p_yes=Probability(0.1),
                outcomes=[OutcomeStr("Yes"), OutcomeStr("No")],
                close_time=utcnow(),
                resolution=Resolution.NO,
                created_time=utcnow() - timedelta(hours=48),
                outcome_token_pool=None,
            )
        ]
        benchmarker = bm.Benchmarker(
            markets=markets,
            agents=[dummy_agent],
            cache_path=cache_path,
        )
        prediction = bm.Prediction(
            outcome_prediction=OutcomePrediction(
                info_utility=0.3333,
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


def test_benchmarker_cancelled_markets() -> None:
    markets = [
        PolymarketAgentMarket(
            description=None,
            id="1",
            volume=None,
            url="url",
            question="Will GNO go up?",
            current_p_yes=Probability(0.1),
            outcomes=[OutcomeStr("Yes"), OutcomeStr("No")],
            close_time=utcnow(),
            created_time=utcnow() - timedelta(hours=48),
            resolution=Resolution.CANCEL,
            outcome_token_pool=None,
        )
    ]
    with pytest.raises(ValueError) as e:
        bm.Benchmarker(
            markets=markets,
            agents=[],
        )
    assert (
        "Unsuccessful markets shouldn't be used in the benchmark, please filter them out."
        in str(e)
    )


def test_market_probable_resolution() -> None:
    with pytest.raises(ValueError) as e:
        PolymarketAgentMarket(
            description=None,
            id="1",
            volume=None,
            url="url",
            question="Will GNO go up?",
            current_p_yes=Probability(0.1),
            outcomes=[OutcomeStr("Yes"), OutcomeStr("No")],
            close_time=utcnow(),
            created_time=utcnow() - timedelta(hours=48),
            resolution=Resolution.CANCEL,
            outcome_token_pool=None,
        ).probable_resolution
    assert "Unknown resolution" in str(e)
    assert (
        PolymarketAgentMarket(
            description=None,
            id="1",
            volume=None,
            url="url",
            question="Will GNO go up?",
            current_p_yes=Probability(0.8),
            outcomes=[OutcomeStr("Yes"), OutcomeStr("No")],
            close_time=utcnow(),
            created_time=utcnow() - timedelta(hours=48),
            resolution=Resolution.YES,
            outcome_token_pool=None,
        ).probable_resolution
        == Resolution.YES
    )
    assert (
        PolymarketAgentMarket(
            description=None,
            id="1",
            volume=None,
            url="url",
            question="Will GNO go up?",
            current_p_yes=Probability(0.1),
            outcomes=[OutcomeStr("Yes"), OutcomeStr("No")],
            close_time=utcnow(),
            resolution=Resolution.NO,
            created_time=utcnow() - timedelta(hours=48),
            outcome_token_pool=None,
        ).probable_resolution
        == Resolution.NO
    )
    assert (
        PolymarketAgentMarket(
            description=None,
            id="1",
            volume=None,
            url="url",
            question="Will GNO go up?",
            current_p_yes=Probability(0.1),
            outcomes=[OutcomeStr("Yes"), OutcomeStr("No")],
            close_time=utcnow(),
            resolution=Resolution.NO,
            created_time=utcnow() - timedelta(hours=48),
            outcome_token_pool=None,
        ).probable_resolution
        == Resolution.NO
    )
    assert (
        PolymarketAgentMarket(
            description=None,
            id="1",
            volume=None,
            url="url",
            question="Will GNO go up?",
            current_p_yes=Probability(0.8),
            outcomes=[OutcomeStr("Yes"), OutcomeStr("No")],
            close_time=utcnow(),
            resolution=Resolution.YES,
            created_time=utcnow() - timedelta(hours=48),
            outcome_token_pool=None,
        ).probable_resolution
        == Resolution.YES
    )
