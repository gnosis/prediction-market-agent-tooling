import numpy as np
import pytest

from prediction_market_agent_tooling.tools.utils import (
    calculate_sell_amount_in_collateral,
)


def test_calculate_sell_amount_in_collateral_0() -> None:
    # Sanity check: If the market is 50/50, then the collateral value of one
    # share is 0.5
    collateral = calculate_sell_amount_in_collateral(
        shares_to_sell=1,
        holdings=1000000000000 - 1,
        other_holdings=1000000000000,
        fee=0,
    )
    assert np.isclose(collateral, 0.5)


def test_calculate_sell_amount_in_collateral_1() -> None:
    # Sanity check that shares have near-zero value with this ratio
    near_zero_collateral = calculate_sell_amount_in_collateral(
        shares_to_sell=1,
        holdings=10000000000000,
        other_holdings=1,
        fee=0,
    )
    assert np.isclose(near_zero_collateral, 0)

    # Sanity check that shares have near-one value with this ratio
    near_zero_collateral = calculate_sell_amount_in_collateral(
        shares_to_sell=1,
        holdings=1,
        other_holdings=10000000000000,
        fee=0,
    )
    assert np.isclose(near_zero_collateral, 1)


def test_calculate_sell_amount_in_collateral_2() -> None:
    # Sanity check: the value of sold shares decreases as the fee increases
    def get_collateral(fee: float) -> float:
        return calculate_sell_amount_in_collateral(
            shares_to_sell=2.5,
            holdings=10,
            other_holdings=3,
            fee=fee,
        )

    c1 = get_collateral(fee=0.1)
    c2 = get_collateral(fee=0.35)
    assert c1 > c2


def test_calculate_sell_amount_in_collateral_3() -> None:
    # Check error handling when fee is invalid
    def get_collateral(fee: float) -> float:
        return calculate_sell_amount_in_collateral(
            shares_to_sell=2.5,
            holdings=10,
            other_holdings=3,
            fee=fee,
        )

    with pytest.raises(ValueError) as e:
        get_collateral(fee=-0.1)
    assert str(e.value) == "Fee must be between 0 and 1"

    with pytest.raises(ValueError) as e:
        get_collateral(fee=1.0)
    assert str(e.value) == "Fee must be between 0 and 1"


def test_calculate_sell_amount_in_collateral_4() -> None:
    with pytest.raises(ValueError) as e:
        collateral = calculate_sell_amount_in_collateral(
            shares_to_sell=100,
            holdings=10,
            other_holdings=0,
            fee=0,
        )
    assert str(e.value) == "All share args must be greater than 0"
