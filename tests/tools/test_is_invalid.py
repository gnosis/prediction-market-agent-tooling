import pytest

from prediction_market_agent_tooling.tools.is_invalid import is_invalid
from tests.utils import RUN_PAID_TESTS


@pytest.mark.skipif(not RUN_PAID_TESTS, reason="This test costs money to run.")
@pytest.mark.parametrize(
    "question, invalid",
    [
        (
            "Russian nuke in space?",
            False,
        ),
        (
            "Russian nuke in space by March 31?",
            False,
        ),
        (
            "Russian nuke in space in 2024?",
            False,
        ),
        (
            "Russian nuke in space in 24 days?",
            True,  # Invalid because the timeframe is relative.
        ),
        (
            "Will there be an AI language model that surpasses ChatGPT and other OpenAI models before the end of 2024?",
            False,
        ),
        ("Will Vladimir Putin be the President of Russia at the end of 2024?", False),
        (
            "This market resolves YES when an artificial agent is appointed to the board of directors of a S&P500 company, meanwhile every day I will bet M25 in NO.",
            False,
        ),
        (
            "Will there be a >0 value liquidity event for me, a former Consensys Software Inc. employee, on my shares of the company?",
            False,
        ),
        (
            "Will this market have an odd number of traders by the end of 2024?",
            False,  # Not invalid, but it should be filtered out by `is_predictable_binary` function.
        ),
        (
            "Did COVID-19 come from a laboratory?",
            False,
        ),
        (
            "What percentile did the median superforecaster get in the 2023 ACX prediction contest?",
            False,  # Not invalid, but should be filtered out by `is_predictable_binary` function as it isn't a Yes/No market.
        ),
        (
            "Will Hezbollah leader Hassan Nasrallah be confirmed dead by 6 October 2024?",
            True,  # Invalid, because this market could motivate people to do it.
        ),
        (
            "Will Netanyahu die before the end of October 7th 2024",
            True,  # Invalid, because this market could motivate people to do it.
        ),
        (
            "Will Travis James Mullis be executed in Texas on 1 October 2024?",
            False,  # Considered okay, becaues execution is done legally by the state, and so this market can not motivate people to do it.
        ),
        (
            "Will the second nitrogen gas execution in Alabama be carried out by 5 October 2024?",
            False,  # Considered okay, becaues execution is done legally by the state, and so this market can not motivate people to do it.
        ),
        (
            "Will someone beat me?",
            True,  # Invalid because it's violent.
        ),
        (
            "Is it okay to hunt?",
            True,  # Invalid because it's about ethicalness.
        ),
    ],
)
def test_is_invalid(question: str, invalid: bool) -> None:
    assert (
        is_invalid(question=question) == invalid
    ), f"Question is not evaluated correctly."
