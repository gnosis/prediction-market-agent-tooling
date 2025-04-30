import pytest

from prediction_market_agent_tooling.gtypes import OutcomeWei, Probability
from prediction_market_agent_tooling.markets.agent_market import AgentMarket


@pytest.mark.parametrize(
    "balances,probabilities",
    [
        ([OutcomeWei(100), OutcomeWei(100)], [Probability(0.5), Probability(0.5)]),
        ([OutcomeWei(200), OutcomeWei(100)], [Probability(1 / 3), Probability(2 / 3)]),
        (
            [OutcomeWei(100), OutcomeWei(100), OutcomeWei(100)],
            [Probability(1 / 3), Probability(1 / 3), Probability(1 / 3)],
        ),
        ([OutcomeWei(0), OutcomeWei(0)], [Probability(0.0), Probability(0.0)]),
        (
            [OutcomeWei(1), OutcomeWei(0), OutcomeWei(0)],
            [Probability(0.0), Probability(0.0), Probability(0.0)],
        ),
    ],
    ids=[
        "equal_balances",
        "unequal_balances",
        "three_outcomes",
        "all_zeros",
        "avoid_division_by_zero",
    ],
)
def test_fpmm_probabilities(
    balances: list[OutcomeWei], probabilities: list[Probability]
) -> None:
    assert AgentMarket.compute_fpmm_probabilities(balances=balances) == probabilities
