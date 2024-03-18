from datetime import datetime

import numpy as np
import pytest
from eth_typing import HexAddress, HexStr
from web3 import Web3

from prediction_market_agent_tooling.gtypes import (
    OmenOutcomeToken,
    Probability,
    Wei,
    usd_type,
    wei_type,
    xDai,
    xdai_type,
)
from prediction_market_agent_tooling.markets.betting_strategies import (
    minimum_bet_to_win,
)
from prediction_market_agent_tooling.markets.manifold.manifold import (
    ManifoldAgentMarket,
)
from prediction_market_agent_tooling.markets.omen.data_models import (
    Condition,
    OmenMarket,
    Question,
)
from prediction_market_agent_tooling.markets.omen.omen import OmenAgentMarket
from prediction_market_agent_tooling.markets.omen.omen_contracts import (
    OmenCollateralTokenContract,
)
from prediction_market_agent_tooling.tools.betting_strategies.kelly_criterion import (
    get_kelly_criterion_bet,
)
from prediction_market_agent_tooling.tools.betting_strategies.market_moving import (
    get_market_moving_bet,
)


@pytest.fixture
def omen_market() -> OmenMarket:
    return OmenMarket(
        id=HexAddress(HexStr("0x76a7a3487f85390dc568f3fce01e0a649cb39651")),
        title="Will Plex launch a store for movies and TV shows by 26 January 2024?",
        collateralVolume=Wei(4369016776639073062),
        usdVolume=usd_type("4.369023756584789670441178585394842"),
        collateralToken=HexAddress(
            HexStr("0xe91d153e0b41518a2ce8dd3d7944fa863463a97d")
        ),
        outcomes=["Yes", "No"],
        outcomeTokenAmounts=[
            OmenOutcomeToken(7277347438897016099),
            OmenOutcomeToken(13741270543921756242),
        ],
        outcomeTokenMarginalPrices=[
            xdai_type("0.6537666061181695741160552853310822"),
            xdai_type("0.3462333938818304258839447146689178"),
        ],
        fee=wei_type(20000000000000000),
        category="foo",
        condition=Condition(id=HexAddress(HexStr("0x123")), outcomeSlotCount=2),
        question=Question(id=HexAddress(HexStr("0x123"))),
    )


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
            collateral_token_contract_address_checksummed=OmenCollateralTokenContract().address,
            market_maker_contract_address_checksummed=Web3.to_checksum_address(
                "0xf3318C420e5e30C12786C4001D600e9EE1A7eBb1"
            ),
            created_time=datetime.now(),
            resolution=None,
            condition=Condition(id=HexAddress(HexStr("0x123")), outcomeSlotCount=2),
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
    min_bet = ManifoldAgentMarket(
        id="id",
        question="question",
        outcomes=["Yes", "No"],
        p_yes=market_p_yes,
        created_time=datetime.now(),
        resolution=None,
    ).get_minimum_bet_to_win(outcome, amount_to_win)
    assert min_bet == expected_min_bet, f"Expected {expected_min_bet}, got {min_bet}."


@pytest.mark.parametrize(
    "wanted_p_yes_on_the_market, expected_buying_xdai_amount, expected_buying_outcome",
    [
        (Probability(0.1), xdai_type(25.32), "No"),
        (Probability(0.9), xdai_type(18.1), "Yes"),
    ],
)
def test_get_market_moving_bet(
    wanted_p_yes_on_the_market: Probability,
    expected_buying_xdai_amount: xDai,
    expected_buying_outcome: str,
    omen_market: OmenMarket,
) -> None:
    xdai_amount, outcome_index = get_market_moving_bet(
        market=omen_market,
        target_p_yes=wanted_p_yes_on_the_market,
        verbose=True,
    )
    assert np.isclose(
        float(xdai_amount),
        float(expected_buying_xdai_amount),
        atol=2.0,  # We don't expect it to be 100% accurate, but close enough.
    ), f"To move this martket to ~{wanted_p_yes_on_the_market}% for yes, the amount should be {expected_buying_xdai_amount}xDai, according to aiomen website."
    assert outcome_index == omen_market.outcomes.index(
        expected_buying_outcome
    ), f"The buying outcome index should `{expected_buying_outcome}`."


@pytest.mark.parametrize(
    "est_p_yes, expected_outcome",
    [
        (Probability(0.1), "No"),
        (Probability(0.9), "Yes"),
    ],
)
def test_kelly_criterion_bet(
    est_p_yes: Probability, expected_outcome: str, omen_market: OmenMarket
) -> None:
    xdai_amount, outcome_index = get_kelly_criterion_bet(
        market=omen_market,
        estimated_p_yes=est_p_yes,
        max_bet=xdai_type(10),  # This significantly changes the outcome.
    )
    # Kelly estimates the best bet for maximizing the expected value of the logarithm of the wealth.
    # We don't know the real best xdai_amount, but at least we know which outcome index makes sense.
    assert outcome_index == omen_market.outcomes.index(expected_outcome)
