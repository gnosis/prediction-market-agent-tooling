import pytest

from prediction_market_agent_tooling.gtypes import (
    CollateralToken,
    OutcomeToken,
    Probability,
)
from prediction_market_agent_tooling.markets.market_fees import MarketFees
from prediction_market_agent_tooling.markets.omen.omen import (
    OmenAgentMarket,
    QuestionType,
    SortBy,
)
from prediction_market_agent_tooling.markets.omen.omen_constants import (
    OMEN_FALSE_OUTCOME,
    OMEN_TRUE_OUTCOME,
)
from prediction_market_agent_tooling.tools.betting_strategies.kelly_criterion import (
    get_kelly_bet_full,
    get_kelly_bet_simplified,
    get_kelly_bets_categorical_full,
    get_kelly_bets_categorical_simplified,
)
from prediction_market_agent_tooling.tools.betting_strategies.utils import (
    BinaryKellyBet,
    CategoricalKellyBet,
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
    "allow_multiple_bets, allow_shorting, multicategorical",
    [
        (True, True, True),
        (True, False, True),
        (False, True, True),
        (False, False, True),
        (True, True, False),
        (True, False, False),
        (False, True, False),
        (False, False, False),
    ],
)
def test_kelly_categorical_full_underpriced(
    allow_multiple_bets: bool, allow_shorting: bool, multicategorical: bool
) -> None:
    # Market [0.79, 0.21], we think [0.9, 0.1] (first outcome underpriced)
    bets = get_kelly_bets_categorical_full(
        outcome_pool_sizes=[
            OutcomeToken(3.598141798265440462),
            OutcomeToken(13.618140347782145810),
        ],
        estimated_probabilities=[Probability(0.9), Probability(0.1)],
        confidence=1.0,
        max_bet=CollateralToken(0.5),
        fees=MarketFees(bet_proportion=0.0, absolute=0.0),
        allow_multiple_bets=allow_multiple_bets,
        allow_shorting=allow_shorting,
        multicategorical=multicategorical,
    )
    assert bets[0].size.value >= 0, bets
    if not multicategorical:
        # In multicategorical case, it could actually be profitable to bet something on second bet as well.
        assert bets[1].size.value <= 0, bets
    assert not all(b.size == 0 for b in bets)
    if not allow_shorting:
        assert all(b.size >= 0 for b in bets)


@pytest.mark.parametrize(
    "allow_multiple_bets, allow_shorting, multicategorical",
    [
        (True, True, True),
        (True, False, True),
        (False, True, True),
        (False, False, True),
        (True, True, False),
        (True, False, False),
        (False, True, False),
        (False, False, False),
    ],
)
def test_kelly_categorical_full_fair_price(
    allow_multiple_bets: bool, allow_shorting: bool, multicategorical: bool
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
        multicategorical=multicategorical,
    )
    assert all(abs(b.size.value) < 1e-6 for b in bets), bets
    if not allow_shorting:
        assert all(b.size >= 0 for b in bets)


@pytest.mark.parametrize(
    "allow_multiple_bets, allow_shorting, multicategorical",
    [
        (True, True, True),
        (True, False, True),
        (False, True, True),
        (False, False, True),
        (True, True, False),
        (True, False, False),
        (False, True, False),
        (False, False, False),
    ],
)
def test_kelly_categorical_full_overpriced(
    allow_multiple_bets: bool, allow_shorting: bool, multicategorical: bool
) -> None:
    # Market [0.79, 0.20], we think [0.4, 0.6] (first outcome overpriced)
    bets = get_kelly_bets_categorical_full(
        outcome_pool_sizes=[
            OutcomeToken(3.598141798265440462),
            OutcomeToken(13.618140347782145810),
        ],
        estimated_probabilities=[Probability(0.4), Probability(0.6)],
        confidence=1.0,
        max_bet=CollateralToken(1),
        fees=MarketFees(bet_proportion=0.0, absolute=0.0),
        allow_multiple_bets=allow_multiple_bets,
        allow_shorting=allow_shorting,
        multicategorical=multicategorical,
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


def _compare_bets(
    market: OmenAgentMarket,
    categorical_bets: list[CategoricalKellyBet],
    binary_bet: BinaryKellyBet,
    max_divergence: float,
) -> None:
    non_zero_categorical_bets = [b for b in categorical_bets if abs(b.size.value) > 0]
    assert (
        len(non_zero_categorical_bets) == 1
    ), f"Unexpected amount of bets in {categorical_bets=}"

    category_bet = non_zero_categorical_bets[0]

    # If one bets, other should as well, binary's kelly size is always positive
    assert (abs(category_bet.size) > 0) == (binary_bet.size > 0), (
        category_bet,
        binary_bet,
        market.url,
    )
    # Index zero on Omen markets is generally Yes, ie True direction of binary kelly, this works only if shorting is disabled.
    assert (category_bet.index == 0) == binary_bet.direction
    # For binary market, they shouldn't differ too much in the sizes
    divergence = abs(category_bet.size.value - binary_bet.size.value) / max(
        category_bet.size.value, binary_bet.size.value
    )
    assert divergence < max_divergence, (
        divergence,
        category_bet,
        binary_bet,
        market.url,
    )


@pytest.mark.parametrize(
    "estimated_p_yes, confidence",
    [
        (0.1, 0.7),
        (0.5, 0.9),
        (0.9, 1.0),
    ],
)
def test_compare_kellys_simplified(
    estimated_p_yes: Probability, confidence: float
) -> None:
    max_bet = CollateralToken(5)
    markets = OmenAgentMarket.get_markets(
        limit=5, sort_by=SortBy.NONE, question_type=QuestionType.BINARY
    )
    for market in markets:
        categorical_bets = get_kelly_bets_categorical_simplified(
            market_probabilities=[market.p_yes, market.p_no],
            estimated_probabilities=[estimated_p_yes, Probability(1 - estimated_p_yes)],
            confidence=confidence,
            max_bet=max_bet,
            # Set as zero to be comparable with binary version.
            fees=MarketFees.get_zero_fees(),
            # Set to False to be comparable with binary version.
            allow_multiple_bets=False,
            allow_shorting=False,
        )
        binary_bet = get_kelly_bet_simplified(
            max_bet=max_bet,
            market_p_yes=market.p_yes,
            estimated_p_yes=estimated_p_yes,
            confidence=confidence,
        )
        _compare_bets(market, categorical_bets, binary_bet, 0.01)


@pytest.mark.parametrize(
    "estimated_p_yes, confidence",
    [
        (0.1, 0.7),
        (0.9, 1.0),
    ],
)
def test_compare_kellys_full(estimated_p_yes: Probability, confidence: float) -> None:
    max_bet = CollateralToken(5)
    markets = OmenAgentMarket.get_markets(
        limit=5, sort_by=SortBy.NONE, question_type=QuestionType.BINARY
    )
    for market in markets:
        categorical_bets = get_kelly_bets_categorical_full(
            outcome_pool_sizes=[market.outcome_token_pool[o] for o in market.outcomes],
            estimated_probabilities=[estimated_p_yes, Probability(1 - estimated_p_yes)],
            confidence=confidence,
            max_bet=max_bet,
            fees=market.fees,
            # Set to False to be comparable with binary version.
            allow_multiple_bets=False,
            allow_shorting=False,
            multicategorical=False,
        )
        binary_bet = get_kelly_bet_full(
            yes_outcome_pool_size=market.outcome_token_pool[OMEN_TRUE_OUTCOME],
            no_outcome_pool_size=market.outcome_token_pool[OMEN_FALSE_OUTCOME],
            estimated_p_yes=estimated_p_yes,
            confidence=confidence,
            max_bet=max_bet,
            fees=market.fees,
        )
        _compare_bets(market, categorical_bets, binary_bet, 0.99)
