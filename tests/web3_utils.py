from typing import Any

import pytest

from prediction_market_agent_tooling.gtypes import Wei
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
