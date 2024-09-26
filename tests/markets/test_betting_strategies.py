from datetime import timedelta

import numpy as np
import pytest
from eth_typing import HexAddress, HexStr
from web3 import Web3

from prediction_market_agent_tooling.gtypes import (
    HexBytes,
    Mana,
    Probability,
    Wei,
    mana_type,
    omen_outcome_type,
    usd_type,
    wei_type,
    xdai_type,
)
from prediction_market_agent_tooling.markets.agent_market import FilterBy, SortBy
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
    WrappedxDaiContract,
)
from prediction_market_agent_tooling.tools.betting_strategies.kelly_criterion import (
    get_kelly_bet_full,
    get_kelly_bet_simplified,
)
from prediction_market_agent_tooling.tools.betting_strategies.market_moving import (
    _sanity_check_omen_market_moving_bet,
    get_market_moving_bet,
)
from prediction_market_agent_tooling.tools.betting_strategies.minimum_bet_to_win import (
    minimum_bet_to_win,
)
from prediction_market_agent_tooling.tools.betting_strategies.stretch_bet_between import (
    stretch_bet_between,
)
from prediction_market_agent_tooling.tools.utils import check_not_none, utcnow
from prediction_market_agent_tooling.tools.web3_utils import wei_to_xdai

GANACHE_ADDRESS_NR_1 = HexAddress(
    Web3.to_checksum_address("0x9B7bc47837d4061a11389267C06D829c5C97E404")
)


@pytest.fixture
def omen_market() -> OmenMarket:
    return OmenMarket(
        id=HexAddress(HexStr("0x76a7a3487f85390dc568f3fce01e0a649cb39651")),
        title="Will Plex launch a store for movies and TV shows by 26 January 2024?",
        creator=GANACHE_ADDRESS_NR_1,
        collateralVolume=Wei(4369016776639073062),
        usdVolume=usd_type("4.369023756584789670441178585394842"),
        collateralToken=HexAddress(
            HexStr("0xe91d153e0b41518a2ce8dd3d7944fa863463a97d")
        ),
        outcomes=["Yes", "No"],
        outcomeTokenAmounts=[
            omen_outcome_type(7277347438897016099),
            omen_outcome_type(13741270543921756242),
        ],
        outcomeTokenMarginalPrices=[
            xdai_type("0.6537666061181695741160552853310822"),
            xdai_type("0.3462333938818304258839447146689178"),
        ],
        fee=wei_type(20000000000000000),
        category="foo",
        condition=Condition(id=HexBytes("0x123"), outcomeSlotCount=2),
        question=Question(
            id=HexBytes("0x123"),
            title="title",
            outcomes=["Yes", "No"],
            templateId=2,
            isPendingArbitration=False,
            data="...",
            openingTimestamp=int(utcnow().timestamp()),
        ),
        liquidityParameter=Wei(10),
        creationTimestamp=int(utcnow().timestamp()),
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
            creator=GANACHE_ADDRESS_NR_1,
            outcomes=["Yes", "No"],
            current_p_yes=market_p_yes,
            collateral_token_contract_address_checksummed=WrappedxDaiContract().address,
            market_maker_contract_address_checksummed=Web3.to_checksum_address(
                "0xf3318C420e5e30C12786C4001D600e9EE1A7eBb1"
            ),
            created_time=utcnow() - timedelta(days=1),
            close_time=utcnow(),
            resolution=None,
            condition=Condition(id=HexBytes("0x123"), outcomeSlotCount=2),
            url="url",
            volume=None,
            finalized_time=None,
            fee=0.02,
            outcome_token_pool=None,
        ),
    )
    assert (
        min_bet / (market_p_yes if outcome else 1 - market_p_yes)
        >= min_bet + amount_to_win
    )


@pytest.mark.parametrize(
    "outcome, market_p_yes, amount_to_win, expected_min_bet",
    [
        (True, 0.68, 1, mana_type(3)),
        (False, 0.68, 1, mana_type(1)),
    ],
)
def test_minimum_bet_to_win_manifold(
    outcome: bool,
    market_p_yes: Probability,
    amount_to_win: float,
    expected_min_bet: Mana,
) -> None:
    min_bet = ManifoldAgentMarket(
        id="id",
        question="question",
        description=None,
        outcomes=["Yes", "No"],
        current_p_yes=market_p_yes,
        created_time=utcnow() - timedelta(days=1),
        close_time=utcnow(),
        resolution=None,
        url="url",
        volume=None,
        outcome_token_pool=None,
    ).get_minimum_bet_to_win(outcome, amount_to_win)
    assert min_bet == expected_min_bet, f"Expected {expected_min_bet}, got {min_bet}."


@pytest.mark.parametrize(
    "target_p_yes, expected_bet_size, expected_bet_direction",
    [
        (Probability(0.1), xdai_type(23.19), False),
        (Probability(0.9), xdai_type(18.1), True),
    ],
)
def test_get_market_moving_bet(
    target_p_yes: Probability,
    expected_bet_size: float,
    expected_bet_direction: bool,
    omen_market: OmenMarket,
) -> None:
    bet = get_market_moving_bet(
        target_p_yes=target_p_yes,
        market_p_yes=omen_market.current_p_yes,
        yes_outcome_pool_size=wei_to_xdai(
            Wei(omen_market.outcomeTokenAmounts[omen_market.yes_index])
        ),
        no_outcome_pool_size=wei_to_xdai(
            Wei(omen_market.outcomeTokenAmounts[omen_market.no_index])
        ),
        fee=wei_to_xdai(check_not_none(omen_market.fee)),
    )
    assert np.isclose(
        bet.size,
        expected_bet_size,
        atol=2.0,  # We don't expect it to be 100% accurate, but close enough.
    )
    assert bet.direction == expected_bet_direction


@pytest.mark.parametrize("target_p_yes", [0.1, 0.51, 0.9])
def test_sanity_check_market_moving_bet(target_p_yes: float) -> None:
    market = OmenAgentMarket.get_binary_markets(
        limit=1,
        sort_by=SortBy.CLOSING_SOONEST,
        filter_by=FilterBy.OPEN,
    )[0]

    outcome_token_pool = check_not_none(market.outcome_token_pool)
    yes_outcome_pool_size = outcome_token_pool[market.get_outcome_str_from_bool(True)]
    no_outcome_pool_size = outcome_token_pool[market.get_outcome_str_from_bool(False)]

    market_moving_bet = get_market_moving_bet(
        yes_outcome_pool_size=yes_outcome_pool_size,
        no_outcome_pool_size=no_outcome_pool_size,
        market_p_yes=market.current_p_yes,
        target_p_yes=target_p_yes,
        fee=market.fee,
    )
    _sanity_check_omen_market_moving_bet(market_moving_bet, market, target_p_yes)


@pytest.mark.parametrize(
    "probability, min_bet, max_bet, expected_bet",
    [
        (Probability(0.1), 0, 1, 0.1),
        (Probability(0.7), 0, 1, 0.7),
        (Probability(0.9), 0.5, 1.0, 0.95),
        (Probability(0.1), 0.5, 1.0, 0.55),
    ],
)
def test_stretch_bet_between(
    probability: Probability, min_bet: float, max_bet: float, expected_bet: float
) -> None:
    assert stretch_bet_between(probability, min_bet, max_bet) == expected_bet


@pytest.mark.parametrize("est_p_yes", [Probability(0.1), Probability(0.9)])
def test_kelly_bet(est_p_yes: Probability, omen_market: OmenMarket) -> None:
    max_bet = 10
    confidence = 1.0
    market_p_yes = omen_market.current_p_yes
    expected_bet_direction = False if est_p_yes < market_p_yes else True

    # Kelly estimates the best bet for maximizing the expected value of the
    # logarithm of the wealth. We don't know the real best bet amount, but at
    # least we know which bet direction makes sense.
    assert (
        get_kelly_bet_simplified(
            market_p_yes=omen_market.current_p_yes,
            estimated_p_yes=est_p_yes,
            max_bet=max_bet,
            confidence=confidence,
        ).direction
        == expected_bet_direction
    )

    assert (
        get_kelly_bet_full(
            yes_outcome_pool_size=wei_to_xdai(
                Wei(omen_market.outcomeTokenAmounts[omen_market.yes_index])
            ),
            no_outcome_pool_size=wei_to_xdai(
                Wei(omen_market.outcomeTokenAmounts[omen_market.no_index])
            ),
            estimated_p_yes=est_p_yes,
            max_bet=max_bet,
            confidence=confidence,
        ).direction
        == expected_bet_direction
    )


def test_zero_bets() -> None:
    market = OmenAgentMarket.get_binary_markets(
        limit=1,
        sort_by=SortBy.CLOSING_SOONEST,
        filter_by=FilterBy.OPEN,
    )[0]

    outcome_token_pool = check_not_none(market.outcome_token_pool)
    yes_outcome_pool_size = outcome_token_pool[market.get_outcome_str_from_bool(True)]
    no_outcome_pool_size = outcome_token_pool[market.get_outcome_str_from_bool(False)]

    market_moving_bet = get_market_moving_bet(
        yes_outcome_pool_size=yes_outcome_pool_size,
        no_outcome_pool_size=no_outcome_pool_size,
        market_p_yes=market.current_p_yes,
        target_p_yes=market.current_p_yes,
        fee=market.fee,
    )
    assert np.isclose(market_moving_bet.size, 0.0, atol=1e-4)

    kelly_bet = get_kelly_bet_full(
        yes_outcome_pool_size=yes_outcome_pool_size,
        no_outcome_pool_size=no_outcome_pool_size,
        estimated_p_yes=market.current_p_yes,
        confidence=1.0,
        max_bet=0,
        fee=market.fee,
    )
    assert kelly_bet.size == 0

    kelly_bet_simple = get_kelly_bet_simplified(
        max_bet=100,
        market_p_yes=market.current_p_yes,
        estimated_p_yes=market.current_p_yes,
        confidence=1.0,
    )
    assert kelly_bet_simple.size == 0
