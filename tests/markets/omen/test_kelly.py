import numpy as np

from prediction_market_agent_tooling.deploy.betting_strategy import KellyBettingStrategy


def test_kelly_slippage_calculation1() -> None:
    # First case from https://docs.gnosis.io/conditionaltokens/docs/introduction3/#an-example-with-cpmm
    kelly = KellyBettingStrategy(max_bet_amount=1, max_slippage=0.5)
    yes = 10
    no = 10
    bet_amount = 10
    buy_direction = True
    assert_slip_ok(bet_amount, buy_direction, yes, no, kelly)


def test_kelly_slippage_calculation2() -> None:
    kelly = KellyBettingStrategy(max_bet_amount=1, max_slippage=0.5)
    # after first bet 10 xDAI on Yes, new yes/no
    yes = 5
    no = 20
    bet_amount = 10
    buy_direction = False
    assert_slip_ok(bet_amount, buy_direction, yes, no, kelly)


def assert_slip_ok(
    bet_amount: float,
    buy_direction: bool,
    yes: float,
    no: float,
    kelly: KellyBettingStrategy,
):
    # expect
    expected_price = yes / (yes + no)  # p_yes
    tokens_bought = (no + bet_amount) - (
        (yes * no) / (yes + bet_amount)
    )  # 23.333 # x*y = k
    actual_price = bet_amount / tokens_bought
    expected_slip = (actual_price - expected_price) / expected_price
    ####
    slip = kelly.calculate_slippage_for_bet_amount(
        buy_direction, bet_amount=bet_amount, yes=yes, no=no, fee=0
    )
    assert np.isclose(slip, expected_slip, rtol=0.01)

    print(slip)
