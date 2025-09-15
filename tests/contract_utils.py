from typing import Any

import pytest
from web3 import Web3

from prediction_market_agent_tooling.gtypes import ChecksumAddress, Wei
from prediction_market_agent_tooling.markets.omen.omen_contracts import (
    SDAI_CONTRACT_ADDRESS,
    WRAPPED_XDAI_CONTRACT_ADDRESS,
)
from prediction_market_agent_tooling.tools.contract_utils import (
    is_erc20_contract,
    is_nft_contract,
)
from prediction_market_agent_tooling.tools.web3_utils import parse_function_params


@pytest.mark.parametrize(
    "input_params, expected_output",
    [
        (((Wei(1), Wei(2), Wei(3)),), ((1, 2, 3),)),  # Tuple of Wei values
        (None, []),  # None input
        ([Wei(1), Wei(2)], [1, 2]),  # List of Wei values
        ({"a": Wei(1), "b": Wei(2)}, [1, 2]),  # Dict with Wei values
        ([], []),  # Empty list
        ({}, []),  # Empty dict
        (((Wei(1)), (Wei(2))), (1, 2)),  # List of lists with Wei values
        (
            (
                "0xaf204776c7245bF4147c2612BF6e5972Ee483701",
                "0xa95BfD1e35D1Ce9906A92108A96ccEe1101aBfaa",
                "0xf39Fd6e51aad88F6F4ce6aB8827279cffFb92266",
                1748545931,
                Wei(847345480336936448),
                Wei(2005356025290512384),
                Wei(0),
            ),
            (
                (
                    "0xaf204776c7245bF4147c2612BF6e5972Ee483701",
                    "0xa95BfD1e35D1Ce9906A92108A96ccEe1101aBfaa",
                    "0xf39Fd6e51aad88F6F4ce6aB8827279cffFb92266",
                    1748545931,
                    847345480336936448,
                    2005356025290512384,
                    0,
                )
            ),  # tuple of tuples
        ),
    ],
)
def test_parse_function_params(
    input_params: list[Any] | tuple[Any] | dict[str, Any],
    expected_output: list[Any] | tuple[Any] | dict[str, Any],
) -> None:
    result = parse_function_params(input_params)
    assert result == expected_output


@pytest.mark.parametrize(
    "addr, is_erc20",
    [
        (WRAPPED_XDAI_CONTRACT_ADDRESS, True),
        (SDAI_CONTRACT_ADDRESS, True),
        (Web3.to_checksum_address("0x0D7C0Bd4169D090038c6F41CFd066958fe7619D0"), False),
    ],
)
def test_is_erc20_contract(addr: ChecksumAddress, is_erc20: bool) -> None:
    assert is_erc20_contract(addr) == is_erc20


@pytest.mark.parametrize(
    "addr, is_nft",
    [
        (WRAPPED_XDAI_CONTRACT_ADDRESS, False),
        (SDAI_CONTRACT_ADDRESS, False),
        (Web3.to_checksum_address("0x0D7C0Bd4169D090038c6F41CFd066958fe7619D0"), True),
    ],
)
def test_is_nft_contract(addr: ChecksumAddress, is_nft: bool) -> None:
    assert is_nft_contract(addr) == is_nft
