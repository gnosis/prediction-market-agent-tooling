import tempfile
from datetime import timedelta

import pytest

import prediction_market_agent_tooling.benchmark.benchmark as bm
from prediction_market_agent_tooling.gtypes import USD, OutcomeStr, Probability
from prediction_market_agent_tooling.markets.data_models import (
    CategoricalProbabilisticAnswer,
    Resolution,
)
from prediction_market_agent_tooling.markets.omen.data_models import (
    OMEN_FALSE_OUTCOME,
    OMEN_TRUE_OUTCOME,
)
from prediction_market_agent_tooling.markets.polymarket.polymarket import (
    PolymarketAgentMarket,
)
from prediction_market_agent_tooling.tools.hexbytes_custom import HexBytes
from prediction_market_agent_tooling.tools.utils import utcnow

MOCK_CONDITION_ID = HexBytes(
    "0x9deb0baac40648821f96f01339229a422e2f5c877de55dc4dbf981f95a1e709c"  # web3-private-key-ok
)


class DummyAgent(bm.AbstractBenchmarkedAgent):
    def __init__(self) -> None:
        super().__init__(agent_name="dummy")

    def check_and_predict(self, market_question: str) -> bm.Prediction:
        return bm.Prediction(
            is_predictable=True,
            outcome_prediction=CategoricalProbabilisticAnswer(
                probabilities={
                    OMEN_TRUE_OUTCOME: Probability(0.6),
                    OMEN_FALSE_OUTCOME: Probability(0.4),
                },
                confidence=0.8,
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
    question = "Will GNO go up?"
    prediction = dummy_agent.check_and_predict(market_question=question)
    assert prediction.outcome_prediction is not None
    assert prediction.outcome_prediction.probabilities[OutcomeStr("Yes")] == 0.6
    assert prediction.outcome_prediction.confidence == 0.8


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
                probabilities={
                    OutcomeStr("Yes"): Probability(0.1),
                    OutcomeStr("No"): Probability(0.9),
                },
                close_time=utcnow() + timedelta(hours=48),
                resolution=None,
                created_time=utcnow() - timedelta(hours=48),
                outcome_token_pool=None,
                condition_id=MOCK_CONDITION_ID,
                liquidity_usd=USD(1),
                token_ids=[1, 2],
                closed_flag_from_polymarket=False,
                active_flag_from_polymarket=True,
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
                    outcome_prediction=CategoricalProbabilisticAnswer(
                        probabilities={
                            OutcomeStr("Yes"): Probability(0.6),
                            OutcomeStr("No"): Probability(0.4),
                        },
                        reasoning="",
                        confidence=0.8,
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
                probabilities={
                    OutcomeStr("Yes"): Probability(0.1),
                    OutcomeStr("No"): Probability(0.9),
                },
                outcomes=[OutcomeStr("Yes"), OutcomeStr("No")],
                close_time=utcnow(),
                resolution=Resolution(outcome=OutcomeStr("No"), invalid=False),
                created_time=utcnow() - timedelta(hours=48),
                outcome_token_pool=None,
                condition_id=MOCK_CONDITION_ID,
                liquidity_usd=USD(1),
                token_ids=[1, 2],
                closed_flag_from_polymarket=False,
                active_flag_from_polymarket=True,
            )
        ]
        benchmarker = bm.Benchmarker(
            markets=markets,
            agents=[dummy_agent],
            cache_path=cache_path,
        )
        prediction = bm.Prediction(
            outcome_prediction=CategoricalProbabilisticAnswer(
                confidence=0.22222, probabilities={}
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
            first_benchmark_prediction.outcome_prediction.probabilities
            == prediction.outcome_prediction.probabilities
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
            another_benchmark_prediction.outcome_prediction.probabilities
            == prediction.outcome_prediction.probabilities
        )
        another_benchmarker.run_agents()

        # Observe that the cached result is still the same
        assert (
            another_benchmark_prediction.outcome_prediction.probabilities
            == prediction.outcome_prediction.probabilities
        )


def test_benchmarker_cancelled_markets() -> None:
    markets = [
        PolymarketAgentMarket(
            description=None,
            id="1",
            volume=None,
            url="url",
            question="Will GNO go up?",
            probabilities={
                OutcomeStr("Yes"): Probability(0.1),
                OutcomeStr("No"): Probability(0.9),
            },
            outcomes=[OutcomeStr("Yes"), OutcomeStr("No")],
            close_time=utcnow(),
            created_time=utcnow() - timedelta(hours=48),
            resolution=Resolution(outcome=None, invalid=True),
            outcome_token_pool=None,
            condition_id=MOCK_CONDITION_ID,
            liquidity_usd=USD(1),
            token_ids=[1, 2],
            closed_flag_from_polymarket=False,
            active_flag_from_polymarket=True,
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
            probabilities={
                OutcomeStr("Yes"): Probability(0.1),
                OutcomeStr("No"): Probability(0.9),
            },
            outcomes=[OutcomeStr("Yes"), OutcomeStr("No")],
            close_time=utcnow(),
            created_time=utcnow() - timedelta(hours=48),
            resolution=Resolution(outcome=None, invalid=True),
            outcome_token_pool=None,
            condition_id=MOCK_CONDITION_ID,
            liquidity_usd=USD(1),
            token_ids=[1, 2],
            closed_flag_from_polymarket=False,
            active_flag_from_polymarket=True,
        ).probable_resolution
    assert "Unknown resolution" in str(e)
    assert PolymarketAgentMarket(
        description=None,
        id="1",
        volume=None,
        url="url",
        question="Will GNO go up?",
        probabilities={
            OutcomeStr("Yes"): Probability(0.8),
            OutcomeStr("No"): Probability(0.2),
        },
        outcomes=[OutcomeStr("Yes"), OutcomeStr("No")],
        close_time=utcnow(),
        created_time=utcnow() - timedelta(hours=48),
        resolution=Resolution(outcome=OutcomeStr("Yes"), invalid=False),
        outcome_token_pool=None,
        condition_id=MOCK_CONDITION_ID,
        liquidity_usd=USD(1),
        token_ids=[1, 2],
        closed_flag_from_polymarket=False,
        active_flag_from_polymarket=True,
    ).probable_resolution == Resolution(outcome=OutcomeStr("Yes"), invalid=False)
    assert PolymarketAgentMarket(
        description=None,
        id="1",
        volume=None,
        url="url",
        question="Will GNO go up?",
        probabilities={
            OutcomeStr("Yes"): Probability(0.1),
            OutcomeStr("No"): Probability(0.9),
        },
        outcomes=[OutcomeStr("Yes"), OutcomeStr("No")],
        close_time=utcnow(),
        resolution=Resolution(outcome=OutcomeStr("No"), invalid=False),
        created_time=utcnow() - timedelta(hours=48),
        outcome_token_pool=None,
        condition_id=MOCK_CONDITION_ID,
        liquidity_usd=USD(1),
        token_ids=[1, 2],
        closed_flag_from_polymarket=False,
        active_flag_from_polymarket=True,
    ).probable_resolution == Resolution(outcome=OutcomeStr("No"), invalid=False)
    assert PolymarketAgentMarket(
        description=None,
        id="1",
        volume=None,
        url="url",
        question="Will GNO go up?",
        probabilities={
            OutcomeStr("Yes"): Probability(0.1),
            OutcomeStr("No"): Probability(0.9),
        },
        outcomes=[OutcomeStr("Yes"), OutcomeStr("No")],
        close_time=utcnow(),
        resolution=Resolution(outcome=OutcomeStr("No"), invalid=False),
        created_time=utcnow() - timedelta(hours=48),
        outcome_token_pool=None,
        condition_id=MOCK_CONDITION_ID,
        liquidity_usd=USD(1),
        token_ids=[1, 2],
        closed_flag_from_polymarket=False,
        active_flag_from_polymarket=True,
    ).probable_resolution == Resolution(outcome=OutcomeStr("No"), invalid=False)
    assert PolymarketAgentMarket(
        description=None,
        id="1",
        volume=None,
        url="url",
        question="Will GNO go up?",
        probabilities={
            OutcomeStr("Yes"): Probability(0.8),
            OutcomeStr("No"): Probability(0.2),
        },
        outcomes=[OutcomeStr("Yes"), OutcomeStr("No")],
        close_time=utcnow(),
        resolution=Resolution(outcome=OutcomeStr("Yes"), invalid=False),
        created_time=utcnow() - timedelta(hours=48),
        outcome_token_pool=None,
        condition_id=MOCK_CONDITION_ID,
        liquidity_usd=USD(1),
        token_ids=[1, 2],
        closed_flag_from_polymarket=False,
        active_flag_from_polymarket=True,
    ).probable_resolution == Resolution(outcome=OutcomeStr("Yes"), invalid=False)
