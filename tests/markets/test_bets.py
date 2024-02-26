import pytest
from web3 import Web3

from prediction_market_agent_tooling.gtypes import Probability
from prediction_market_agent_tooling.markets.betting_strategies import (
    minimum_bet_to_win,
    minimum_bet_to_win_manifold,
)
from prediction_market_agent_tooling.markets.manifold.manifold import (
    ManifoldAgentMarket,
)
from prediction_market_agent_tooling.markets.omen.omen import OmenAgentMarket
from prediction_market_agent_tooling.tools.web3_utils import WXDAI_CONTRACT_ADDRESS


@pytest.mark.parametrize(
    "outcome, market_p_yes, amount_to_win",
    [
        (True, 0.68, 1),
        (False, 0.68, 1),
        (True, 0.7, 10),
    ],
)
def test_minimum_bet_to_win(
    outcome: bool, market_p_yes: Probability, amount_to_win: float
) -> None:
    min_bet = minimum_bet_to_win(
        outcome,
        amount_to_win,
        OmenAgentMarket(
            id="id",
            question="question",
            outcomes=["Yes", "No"],
            p_yes=market_p_yes,
            collateral_token_contract_address_checksummed=WXDAI_CONTRACT_ADDRESS,
            market_maker_contract_address_checksummed=Web3.to_checksum_address(
                "0xf3318C420e5e30C12786C4001D600e9EE1A7eBb1"
            ),
        ),
    )
    assert (
        min_bet / (market_p_yes if outcome else 1 - market_p_yes)
        >= min_bet + amount_to_win
    )


@pytest.mark.parametrize(
    "outcome, market_p_yes, amount_to_win, expected_min_bet",
    [
        (True, 0.68, 1, 3),
        (False, 0.68, 1, 1),
    ],
)
def test_minimum_bet_to_win_manifold(
    outcome: bool,
    market_p_yes: Probability,
    amount_to_win: float,
    expected_min_bet: int,
) -> None:
    min_bet = minimum_bet_to_win_manifold(
        outcome,
        amount_to_win,
        ManifoldAgentMarket(
            id="id",
            question="question",
            outcomes=["Yes", "No"],
            p_yes=market_p_yes,
        ),
    )
    assert min_bet == expected_min_bet, f"Expected {expected_min_bet}, got {min_bet}."
