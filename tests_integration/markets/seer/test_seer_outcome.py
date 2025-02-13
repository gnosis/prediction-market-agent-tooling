import pytest

from prediction_market_agent_tooling.markets.seer.data_models import SeerOutcomeEnum


@pytest.mark.parametrize("outcome", ["YES", "NO", "INVALID"])
def test_seer_outcome(outcome: str) -> None:
    assert SeerOutcomeEnum.from_string(outcome.lower()) == SeerOutcomeEnum.from_string(
        outcome
    )
    assert SeerOutcomeEnum.from_string(
        outcome.capitalize()
    ) == SeerOutcomeEnum.from_string(outcome)


def test_seer_outcome_invalid() -> None:
    assert SeerOutcomeEnum.from_string("Invalid result") == SeerOutcomeEnum.NEUTRAL
