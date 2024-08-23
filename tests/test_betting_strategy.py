import pytest

from prediction_market_agent_tooling.deploy.betting_strategy import (
    MaxAccuracyBettingStrategy,
)


@pytest.mark.parametrize(
    "estimate_p_yes, market_p_yes, expected_direction",
    [
        (0.6, 0.5, True),
        (0.4, 0.5, False),
    ],
)
def test_answer_decision(
    estimate_p_yes: float, market_p_yes: float, expected_direction: bool
) -> None:
    betting_strategy = MaxAccuracyBettingStrategy()
    direction: bool = betting_strategy.calculate_direction(market_p_yes, estimate_p_yes)
    assert direction == expected_direction
