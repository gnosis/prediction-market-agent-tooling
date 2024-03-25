import pytest
from eth_typing import HexAddress, HexStr


@pytest.fixture(scope="module")
def a_bet_from_address() -> str:
    return "0x3666DA333dAdD05083FEf9FF6dDEe588d26E4307"


@pytest.fixture(scope="module")
def agent0_address() -> str:
    return "0x2DD9f5678484C1F59F97eD334725858b938B4102"
