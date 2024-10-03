import numpy as np

from prediction_market_agent_tooling.deploy.betting_strategy import KellyBettingStrategy


def test_kelly_price_impact_calculation1() -> None:
    # First case from https://docs.gnosis.io/conditionaltokens/docs/introduction3/#an-example-with-cpmm
    kelly = KellyBettingStrategy(max_bet_amount=1, max_price_impact=0.5)
    yes = 10
    no = 10
    bet_amount = 10
    buy_direction = True
    assert_price_impact(bet_amount, buy_direction, yes, no, kelly)


def test_kelly_price_impact_calculation2() -> None:
    # Follow-up from first case from https://docs.gnosis.io/conditionaltokens/docs/introduction3/#an-example-with-cpmm
    kelly = KellyBettingStrategy(max_bet_amount=1, max_price_impact=0.5)
    # after first bet 10 xDAI on Yes, new yes/no
    yes = 5
    no = 20
    bet_amount = 10
    buy_direction = False
    assert_price_impact(bet_amount, buy_direction, yes, no, kelly)


def assert_price_impact(
    bet_amount: float,
    buy_direction: bool,
    yes: float,
    no: float,
    kelly: KellyBettingStrategy,
) -> None:
    price_impact = kelly.calculate_price_impact_for_bet_amount(
        buy_direction, bet_amount=bet_amount, yes=yes, no=no, fee=0
    )

    # Calculation is done assuming buy_direction is True. Else, we invert the reserves.
    if not buy_direction:
        yes, no = no, yes

    expected_price_yes = no / (yes + no)
    k = yes * no
    tokens_bought_yes = (yes + bet_amount) - (k / (no + bet_amount))  # 23.333 # x*y = k
    actual_price_yes = bet_amount / tokens_bought_yes
    expected_price_impact = (actual_price_yes - expected_price_yes) / expected_price_yes
    ####

    assert np.isclose(price_impact, expected_price_impact, rtol=0.01)

    print(price_impact)
