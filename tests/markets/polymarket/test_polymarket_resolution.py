import pytest

from prediction_market_agent_tooling.gtypes import OutcomeStr
from prediction_market_agent_tooling.markets.data_models import Resolution
from prediction_market_agent_tooling.markets.polymarket.polymarket import (
    PolymarketAgentMarket,
)
from prediction_market_agent_tooling.markets.polymarket.polymarket_subgraph_handler import (
    ConditionSubgraphModel,
)
from tests.markets.polymarket.conftest import MOCK_CONDITION_ID, MOCK_QUESTION_ID

BINARY_OUTCOMES = [OutcomeStr("Yes"), OutcomeStr("No")]


def _make_condition(**kwargs: object) -> ConditionSubgraphModel:
    defaults = dict(
        id=MOCK_CONDITION_ID,
        payoutDenominator=1,
        payoutNumerators=[1, 0],
        outcomeSlotCount=2,
        resolutionTimestamp=1700000000,
        questionId=MOCK_QUESTION_ID,
    )
    defaults.update(kwargs)
    return ConditionSubgraphModel(**defaults)  # type: ignore[arg-type]


@pytest.mark.parametrize(
    "payout_numerators, outcomes, expected_outcome",
    [
        ([1, 0], BINARY_OUTCOMES, OutcomeStr("Yes")),
        ([0, 1], BINARY_OUTCOMES, OutcomeStr("No")),
    ],
)
def test_binary_resolution(
    payout_numerators: list[int],
    outcomes: list[OutcomeStr],
    expected_outcome: OutcomeStr,
) -> None:
    condition = _make_condition(payoutNumerators=payout_numerators)
    condition_dict = {MOCK_CONDITION_ID: condition}

    result = PolymarketAgentMarket.build_resolution_from_condition(
        condition_id=MOCK_CONDITION_ID,
        condition_model_dict=condition_dict,
        outcomes=outcomes,
    )

    assert result == Resolution.from_answer(expected_outcome)


@pytest.mark.parametrize(
    "condition_override",
    [
        dict(resolutionTimestamp=None),
        dict(payoutNumerators=None),
        dict(payoutDenominator=None),
    ],
    ids=["no_resolution_timestamp", "no_payout_numerators", "no_payout_denominator"],
)
def test_returns_none_for_missing_data(
    condition_override: dict[str, object],
) -> None:
    condition = _make_condition(**condition_override)
    condition_dict = {MOCK_CONDITION_ID: condition}

    result = PolymarketAgentMarket.build_resolution_from_condition(
        condition_id=MOCK_CONDITION_ID,
        condition_model_dict=condition_dict,
        outcomes=BINARY_OUTCOMES,
    )

    assert result is None


def test_condition_not_in_dict() -> None:
    result = PolymarketAgentMarket.build_resolution_from_condition(
        condition_id=MOCK_CONDITION_ID,
        condition_model_dict={},
        outcomes=BINARY_OUTCOMES,
    )

    assert result is None


@pytest.mark.parametrize(
    "payout_numerators, outcomes",
    [
        ([1, 1, 0], [OutcomeStr("A"), OutcomeStr("B"), OutcomeStr("C")]),
        ([0, 0], BINARY_OUTCOMES),
    ],
    ids=["multi_outcome", "all_zero_payouts"],
)
def test_non_binary_resolution(
    payout_numerators: list[int],
    outcomes: list[OutcomeStr],
) -> None:
    condition = _make_condition(
        payoutNumerators=payout_numerators,
        outcomeSlotCount=len(outcomes),
    )
    condition_dict = {MOCK_CONDITION_ID: condition}

    result = PolymarketAgentMarket.build_resolution_from_condition(
        condition_id=MOCK_CONDITION_ID,
        condition_model_dict=condition_dict,
        outcomes=outcomes,
    )

    assert result == Resolution(outcome=None, invalid=False)
