import pytest

from prediction_market_agent_tooling.tools.is_predictable import is_predictable
from tests.utils import RUN_PAID_TESTS


@pytest.mark.skipif(not RUN_PAID_TESTS, reason="This test costs money to run.")
@pytest.mark.parametrize(
    "question, answerable",
    [
        ("Russian nuke in space?", False),
        (
            "Russian nuke in space by March 31?",
            True,
        ),
        (
            "Russian nuke in space in 2024?",
            True,
        ),
        (
            "Will there be an AI language model that surpasses ChatGPT and other OpenAI models before the end of 2024?",
            True,
        ),
        ("Will Vladimir Putin be the President of Russia at the end of 2024?", True),
        (
            "This market resolves YES when an artificial agent is appointed to the board of directors of a S&P500 company, meanwhile every day I will bet M25 in NO.",
            False,
        ),
        (
            "Will there be a >0 value liquidity event for me, a former Consensys Software Inc. employee, on my shares of the company?",
            False,
        ),
        ("Will this market have an odd number of traders by the end of 2024?", False),
        ("Did COVID-19 come from a laboratory?", False),
    ],
)
def test_evaluate_question(question: str, answerable: bool) -> None:
    assert (
        is_predictable(question=question) == answerable
    ), f"Question is not evaluated correctly, see the completion: {is_predictable}"
