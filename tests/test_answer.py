import typing as t

import pytest

from prediction_market_agent_tooling.markets.data_models import ProbabilisticAnswer


@pytest.mark.parametrize(
    "obj, expected_decision",
    [
        ({"decision": "y", "p_yes": 0.1, "confidence": 0.5}, True),
        ({"decision": "1", "p_yes": 0.1, "confidence": 0.5}, True),
        ({"decision": "True", "p_yes": 0.1, "confidence": 0.5}, True),
        ({"decision": "n", "p_yes": 0.1, "confidence": 0.5}, False),
        ({"decision": "0", "p_yes": 0.1, "confidence": 0.5}, False),
        ({"decision": "False", "p_yes": 0.1, "confidence": 0.5}, False),
    ],
)
def test_answer_decision(obj: dict[str, t.Any], expected_decision: bool) -> None:
    assert ProbabilisticAnswer.model_validate(obj).decision == expected_decision
