import pytest
from numpy import isclose

from prediction_market_agent_tooling.gtypes import Probability
from prediction_market_agent_tooling.tools.utils import prob_uncertainty


@pytest.mark.parametrize(
    "prob, expected",
    [
        (Probability(0.5), 1),
        (Probability(0.1), 0.468),
        (Probability(0.95), 0.286),
    ],
)
def test_prob_uncertainty(prob: Probability, expected: float) -> None:
    assert isclose(prob_uncertainty(prob), expected, rtol=0.01)
