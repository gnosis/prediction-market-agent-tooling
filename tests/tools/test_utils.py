import numpy as np

from prediction_market_agent_tooling.gtypes import OutcomeToken
from prediction_market_agent_tooling.markets.market_fees import MarketFees
from prediction_market_agent_tooling.tools.hexbytes_custom import HexBytes
from prediction_market_agent_tooling.tools.utils import (
    calculate_sell_amount_in_collateral,
    answer_to_resolved_outcome_idx,
)


def test_calculate_sell_amount_in_collateral_0() -> None:
    # Sanity check: If the market is 50/50, then the collateral value of one
    # share is 0.5
    collateral = calculate_sell_amount_in_collateral(
        shares_to_sell=OutcomeToken(1),
        outcome_index=0,
        pool_balances=[OutcomeToken(1000000000000 - 1), OutcomeToken(1000000000000)],
        fees=MarketFees.get_zero_fees(),
    )
    assert np.isclose(collateral.value, 0.5)


def test_calculate_sell_amount_in_collateral_1() -> None:
    # Sanity check that shares have near-zero value with this ratio
    near_zero_collateral = calculate_sell_amount_in_collateral(
        shares_to_sell=OutcomeToken(1),
        outcome_index=1,
        pool_balances=[OutcomeToken(1), OutcomeToken(10000000000000)],
        fees=MarketFees.get_zero_fees(),
    )
    assert np.isclose(near_zero_collateral.value, 0)

    # Sanity check that shares have near-one value with this ratio
    near_zero_collateral = calculate_sell_amount_in_collateral(
        shares_to_sell=OutcomeToken(1),
        outcome_index=0,
        pool_balances=[OutcomeToken(1), OutcomeToken(10000000000000)],
        fees=MarketFees.get_zero_fees(),
    )
    assert np.isclose(near_zero_collateral.value, 1)


def test_calculate_sell_amount_in_collateral_2() -> None:
    # Sanity check: the value of sold shares decreases as the fee increases
    def get_collateral(bet_proportion_fee: float) -> float:
        fees = MarketFees.get_zero_fees(bet_proportion=bet_proportion_fee)
        return calculate_sell_amount_in_collateral(
            shares_to_sell=OutcomeToken(2.5),
            outcome_index=0,
            pool_balances=[OutcomeToken(10), OutcomeToken(3)],
            fees=fees,
        ).value

    c1 = get_collateral(bet_proportion_fee=0.1)
    c2 = get_collateral(bet_proportion_fee=0.35)
    assert c1 > c2


def test_calculate_sell_amount_in_collateral_3() -> None:
    # Check error handling when fee is invalid
    def get_collateral(bet_proportion_fee: float) -> float:
        fees = MarketFees.get_zero_fees(bet_proportion=bet_proportion_fee)
        return calculate_sell_amount_in_collateral(
            shares_to_sell=OutcomeToken(2.5),
            outcome_index=0,
            pool_balances=[OutcomeToken(10), OutcomeToken(3)],
            fees=fees,
        ).value

    with pytest.raises(ValueError) as e:
        get_collateral(bet_proportion_fee=-0.1)
    assert "Input should be greater than or equal to 0" in str(e.value)

    with pytest.raises(ValueError) as e:
        get_collateral(bet_proportion_fee=1.0)
    assert "Input should be less than 1" in str(e.value)


def test_calculate_sell_amount_in_collateral_4() -> None:
    with pytest.raises(ValueError) as e:
        collateral = calculate_sell_amount_in_collateral(
            shares_to_sell=OutcomeToken(100),
            outcome_index=0,
            pool_balances=[OutcomeToken(10), OutcomeToken(0)],
            fees=MarketFees.get_zero_fees(),
        )
    assert str(e.value) == f"All pool balances must be greater than 0"


def test_calculate_sell_amount_in_collateral_5() -> None:
    collateral = calculate_sell_amount_in_collateral(
        shares_to_sell=OutcomeToken(0),
        outcome_index=0,
        pool_balances=[OutcomeToken(10), OutcomeToken(15)],
        fees=MarketFees.get_zero_fees(),
    )
    assert collateral == 0


import pytest
from hexbytes import HexBytes


@pytest.mark.parametrize(
    "hex_str, length, expected",
    [
        # multi-categorical
        (
            "0x0000000000000000000000000000000000000000000000000000000000000018",
            6,
            [3, 4],
        ),
        # outcome 0
        ("0x0000000000000000000000000000000000000000000000000000000000000000", 2, [0]),
        # outcome 1
        ("0x0000000000000000000000000000000000000000000000000000000000000001", 2, [1]),
    ],
)
def test_answer_multi_categorical(
    hex_str: str, length: int, expected: list[int]
) -> None:
    answer = HexBytes(hex_str)
    result = answer_to_resolved_outcome_idx(answer, length)
    assert result == expected
