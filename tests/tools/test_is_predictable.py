import pytest

from prediction_market_agent_tooling.tools.is_predictable import (
    is_predictable_binary,
    is_predictable_without_description,
)
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
        (
            "What percentile did the median superforecaster get in the 2023 ACX prediction contest?",
            False,
        ),
    ],
)
def test_is_predictable_binary(question: str, answerable: bool) -> None:
    assert (
        is_predictable_binary(question=question) == answerable
    ), f"Question is not evaluated correctly."


@pytest.mark.skipif(not RUN_PAID_TESTS, reason="This test costs money to run.")
@pytest.mark.parametrize(
    "question, description, answerable",
    [
        (
            "Russian nuke in space?",
            "Will resolve to 'True' if Russian nuke will be in space by the end of 2024.",
            False,  # False, because description clarifies the date 2024.
        ),
        (
            "Russian nuke in space in 2024?",
            "Will resolve to 'True' if Russian nuke will be in space by the end of 2024.",
            True,  # True, because description doesn't provide any extra information.
        ),
        (
            "Will cash withdrawals be enabled before August 1st?",
            "Will Manifold officially enable cash withdrawals to user accounts (not just charities) any time before August 1st, 2024? Cash withdrawals must be an active part of the Manifold UI users could theoretically use.",
            False,  # False, because description provides context about Manifold.
        ),
        (
            "If they play, will Biden beat Trump at golf?",
            "Resolves N/A if they don't play golf before the election.",
            False,  # False, because description provides the time frame.
        ),
        (
            "Will Biden be the 2024 Democratic Nominee?",
            "The resolution is to the first nominee formally selected by the Democratic Party (which happens at the Democratic National Convention). If the nominee is later replaced (for example, due to dropping out of the election, death, etc) that does not change the resolution. If a candidate becomes presumptive nominee after securing a majority of pledged delegates, that is not sufficient for resolution, until formally selected as nominee.",
            False,  # False, because `nominee` could mean multiple things that are clarified in the description.
        ),
        (
            "Will Biden win the 2024 US Presidential Election?",
            "Resolves to the person who wins the majority of votes for US President in the Electoral College, or selected by Congress following the contingency procedure in the Twelfth Amendment.",
            True,  # True, because description doesn't provide any necessary information.
        ),
        (
            "Will an AI get gold on any International Math Olympiad by 2025?",
            "Resolves to YES if either Eliezer or Paul acknowledge that an AI has succeeded at this task.",
            True,  # True, because description doesn't provide any extra information.
        ),
    ],
)
def test_is_predictable_without_description(
    question: str, description: str, answerable: bool
) -> None:
    assert (
        is_predictable_without_description(question=question, description=description)
        == answerable
    ), f"Question is not evaluated correctly."
