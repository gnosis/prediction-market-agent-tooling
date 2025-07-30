import pytest

from prediction_market_agent_tooling.gtypes import (
    CollateralToken,
    OutcomeToken,
    Probability,
)
from prediction_market_agent_tooling.markets.market_fees import MarketFees
from prediction_market_agent_tooling.tools.betting_strategies.kelly_criterion import (
    get_kelly_bet_full,
    get_kelly_bet_simplified,
    get_kelly_bets_categorical_full,
    get_kelly_bets_categorical_simplified,
)


def test_kelly_simplified_underpriced() -> None:
    # Market says 0.4, we think 0.7 (underpriced, should buy)
    bet = get_kelly_bet_simplified(
        max_bet=CollateralToken(1),
        market_p_yes=0.4,
        estimated_p_yes=0.7,
        confidence=1.0,
    )
    assert bet.direction is True
    assert bet.size.value > 0


def test_kelly_simplified_fair_price() -> None:
    # Market and estimate match, bet size should be near zero
    bet = get_kelly_bet_simplified(
        max_bet=CollateralToken(1),
        market_p_yes=0.5,
        estimated_p_yes=0.5,
        confidence=1.0,
    )
    assert abs(bet.size.value) < 1e-6


def test_kelly_simplified_overpriced() -> None:
    # Market says 0.7, we think 0.4 (overpriced, should "sell" or negative bet)
    bet = get_kelly_bet_simplified(
        max_bet=CollateralToken(1),
        market_p_yes=0.7,
        estimated_p_yes=0.4,
        confidence=1.0,
    )
    assert bet.direction is False
    assert bet.size.value > 0  # bet.size is always positive, direction is False


def test_kelly_full_underpriced() -> None:
    # Market says 0.79, we think 0.9 (underpriced, should buy)
    bet = get_kelly_bet_full(
        yes_outcome_pool_size=OutcomeToken(3.598141798265440462),
        no_outcome_pool_size=OutcomeToken(13.618140347782145810),
        estimated_p_yes=0.9,
        confidence=1.0,
        max_bet=CollateralToken(1),
        fees=MarketFees(bet_proportion=0.0, absolute=0.0),
    )
    assert bet.direction is True
    assert bet.size.value > 0


def test_kelly_full_fair_price() -> None:
    # Market and estimate match, bet size should be near zero
    bet = get_kelly_bet_full(
        yes_outcome_pool_size=OutcomeToken(500),
        no_outcome_pool_size=OutcomeToken(500),
        estimated_p_yes=0.5,
        confidence=1.0,
        max_bet=CollateralToken(1),
        fees=MarketFees(bet_proportion=0.0, absolute=0.0),
    )
    assert abs(bet.size.value) < 1e-6


def test_kelly_full_overpriced() -> None:
    # Market says 0.79, we think 0.4 (overpriced, should "sell" or negative bet)
    bet = get_kelly_bet_full(
        yes_outcome_pool_size=OutcomeToken(3.598141798265440462),
        no_outcome_pool_size=OutcomeToken(13.618140347782145810),
        estimated_p_yes=0.4,
        confidence=1.0,
        max_bet=CollateralToken(1),
        fees=MarketFees(bet_proportion=0.0, absolute=0.0),
    )
    assert bet.direction is False
    assert bet.size.value > 0  # bet.size is always positive, direction is False


@pytest.mark.parametrize(
    "allow_multiple_bets, allow_shorting",
    [
        (True, True),
        (True, False),
        (False, True),
        (False, False),
    ],
)
def test_kelly_categorical_simplified_underpriced(
    allow_multiple_bets: bool, allow_shorting: bool
) -> None:
    # Market says [0.2, 0.8], we think [0.7, 0.3] (first outcome underpriced)
    bets = get_kelly_bets_categorical_simplified(
        market_probabilities=[Probability(0.2), Probability(0.8)],
        estimated_probabilities=[Probability(0.7), Probability(0.3)],
        confidence=1.0,
        max_bet=CollateralToken(1),
        fees=MarketFees(bet_proportion=0.0, absolute=0.0),
        allow_multiple_bets=allow_multiple_bets,
        allow_shorting=allow_shorting,
    )
    assert bets[0].size.value >= 0
    assert bets[1].size.value <= 0
    assert not all(b.size == 0 for b in bets)
    if not allow_shorting:
        assert all(b.size >= 0 for b in bets)


@pytest.mark.parametrize(
    "allow_multiple_bets, allow_shorting",
    [
        (True, True),
        (True, False),
        (False, True),
        (False, False),
    ],
)
def test_kelly_categorical_simplified_fair_price(
    allow_multiple_bets: bool, allow_shorting: bool
) -> None:
    # Market and estimate match, all bets should be near zero
    bets = get_kelly_bets_categorical_simplified(
        market_probabilities=[Probability(0.5), Probability(0.5)],
        estimated_probabilities=[Probability(0.5), Probability(0.5)],
        confidence=1.0,
        max_bet=CollateralToken(1),
        fees=MarketFees(bet_proportion=0.0, absolute=0.0),
        allow_multiple_bets=allow_multiple_bets,
        allow_shorting=allow_shorting,
    )
    assert all(abs(b.size.value) < 1e-6 for b in bets)
    if not allow_shorting:
        assert all(b.size >= 0 for b in bets)


@pytest.mark.parametrize(
    "allow_multiple_bets, allow_shorting",
    [
        (True, True),
        (True, False),
        (False, True),
        (False, False),
    ],
)
def test_kelly_categorical_simplified_overpriced(
    allow_multiple_bets: bool, allow_shorting: bool
) -> None:
    # Market says [0.7, 0.3], we think [0.4, 0.6] (first outcome overpriced)
    bets = get_kelly_bets_categorical_simplified(
        market_probabilities=[Probability(0.7), Probability(0.3)],
        estimated_probabilities=[Probability(0.4), Probability(0.6)],
        confidence=1.0,
        max_bet=CollateralToken(1),
        fees=MarketFees(bet_proportion=0.0, absolute=0.0),
        allow_multiple_bets=allow_multiple_bets,
        allow_shorting=allow_shorting,
    )
    assert bets[0].size.value <= 0
    assert bets[1].size.value >= 0
    assert not all(b.size == 0 for b in bets)
    if not allow_shorting:
        assert all(b.size >= 0 for b in bets)


@pytest.mark.parametrize(
    "allow_multiple_bets, allow_shorting",
    [
        (True, True),
        (True, False),
        (False, True),
        (False, False),
    ],
)
def test_kelly_categorical_full_underpriced(
    allow_multiple_bets: bool, allow_shorting: bool
) -> None:
    # Market [0.79, 0.21], we think [0.9, 0.1] (first outcome underpriced)
    bets = get_kelly_bets_categorical_full(
        outcome_pool_sizes=[
            OutcomeToken(3.598141798265440462),
            OutcomeToken(13.618140347782145810),
        ],
        estimated_probabilities=[Probability(0.9), Probability(0.1)],
        confidence=1.0,
        max_bet=CollateralToken(1),
        fees=MarketFees(bet_proportion=0.0, absolute=0.0),
        allow_multiple_bets=allow_multiple_bets,
        allow_shorting=allow_shorting,
    )
    assert bets[0].size.value >= 0, bets
    assert bets[1].size.value <= 0, bets
    assert not all(b.size == 0 for b in bets)
    if not allow_shorting:
        assert all(b.size >= 0 for b in bets)


@pytest.mark.parametrize(
    "allow_multiple_bets, allow_shorting",
    [
        (True, True),
        (True, False),
        (False, True),
        (False, False),
    ],
)
def test_kelly_categorical_full_fair_price(
    allow_multiple_bets: bool, allow_shorting: bool
) -> None:
    # Market pools: [500, 500], we think [0.5, 0.5] (fair)
    bets = get_kelly_bets_categorical_full(
        outcome_pool_sizes=[OutcomeToken(500), OutcomeToken(500)],
        estimated_probabilities=[Probability(0.5), Probability(0.5)],
        confidence=1.0,
        max_bet=CollateralToken(1),
        fees=MarketFees(bet_proportion=0.0, absolute=0.0),
        allow_multiple_bets=allow_multiple_bets,
        allow_shorting=allow_shorting,
    )
    assert all(abs(b.size.value) < 1e-6 for b in bets), bets
    if not allow_shorting:
        assert all(b.size >= 0 for b in bets)


@pytest.mark.parametrize(
    "allow_multiple_bets, allow_shorting",
    [
        (True, True),
        (True, False),
        (False, True),
        (False, False),
    ],
)
def test_kelly_categorical_full_overpriced(
    allow_multiple_bets: bool, allow_shorting: bool
) -> None:
    # Market [0.79, 0.20], we think [0.4, 0.6] (first outcome overpriced)
    bets = get_kelly_bets_categorical_full(
        outcome_pool_sizes=[
            OutcomeToken(3.598141798265440462),
            OutcomeToken(13.618140347782145810),
        ],
        estimated_probabilities=[Probability(0.4), Probability(0.6)],
        confidence=1.0,
        max_bet=CollateralToken(0.5),
        fees=MarketFees(bet_proportion=0.0, absolute=0.0),
        allow_multiple_bets=allow_multiple_bets,
        allow_shorting=allow_shorting,
    )
    assert bets[0].size.value <= 0
    assert bets[1].size.value >= 0
    assert not all(b.size == 0 for b in bets)
    if not allow_shorting:
        assert all(b.size >= 0 for b in bets)


@pytest.mark.parametrize(
    "allow_multiple_bets, allow_shorting",
    [
        (True, True),
        (True, False),
        (False, True),
        (False, False),
    ],
)
def test_kelly_categorical_simplified_0(
    allow_multiple_bets: bool, allow_shorting: bool
) -> None:
    # Market and estimate match, all bets should be near zero
    bets = get_kelly_bets_categorical_simplified(
        market_probabilities=[
            Probability(0.32522134067234254),
            Probability(0.6747786593276575),
        ],
        estimated_probabilities=[Probability(0.2), Probability(0.8)],
        confidence=0.8,
        max_bet=CollateralToken(25),
        fees=MarketFees(bet_proportion=0.02, absolute=0.0),
        allow_multiple_bets=allow_multiple_bets,
        allow_shorting=allow_shorting,
    )
    assert bets[0].size.value <= 0, bets
    assert bets[1].size.value >= 0, bets
    assert not all(b.size == 0 for b in bets), bets
    if not allow_shorting:
        assert all(b.size >= 0 for b in bets), bets
