from typing import Generator

import pytest
from web3 import Web3

from prediction_market_agent_tooling.gtypes import ChecksumAddress
from prediction_market_agent_tooling.markets.omen.omen_contracts import (
    WrappedxDaiContract,
    sDaiContract,
)
from prediction_market_agent_tooling.tools.contract import (
    ContractDepositableWrapperERC20BaseClass,
    ContractERC4626BaseClass,
    ERC20FakeDepositWithdraw,
    contract_implements_function,
    init_collateral_contract,
)


@pytest.fixture(scope="class")
def test_web3() -> Generator[Web3, None, None]:
    yield WrappedxDaiContract.get_web3()


def test_init_erc4626_erc20_contract_return_erc4626_instance(test_web3: Web3) -> None:
    contract = init_collateral_contract(sDaiContract().address, test_web3)
    assert isinstance(
        contract, ContractERC4626BaseClass
    ), f"Returned contract is {type(contract)}"


def test_init_erc4626_erc20_contract_return_wrappererc20_instance(
    test_web3: Web3,
) -> None:
    contract = init_collateral_contract(WrappedxDaiContract().address, test_web3)
    assert isinstance(
        contract, ContractDepositableWrapperERC20BaseClass
    ), f"Returned contract is {type(contract)}"


def test_init_erc4626_erc20_contract_return_erc20_instance(test_web3: Web3) -> None:
    contract = init_collateral_contract(
        Web3.to_checksum_address("0x4ecaba5870353805a9f068101a40e0f32ed605c6"),
        WrappedxDaiContract.get_web3(),
    )
    assert isinstance(
        contract, ERC20FakeDepositWithdraw
    ), f"Returned contract is {type(contract)}"


def test_init_erc4626_erc20_contract_throws_on_unknown_contract(
    test_web3: Web3,
) -> None:
    with pytest.raises(ValueError) as e:
        init_collateral_contract(
            Web3.to_checksum_address("0x7d3A0DA18e14CCb63375cdC250E8A8399997816F"),
            test_web3,
        )
    assert "neither WrapperERC-20 nor ERC-4626" in str(e)


@pytest.mark.parametrize(
    "contract_address, function_name, function_arg_types, web3_fixture, expected",
    [
        (
            WrappedxDaiContract().address,
            "balanceOf",
            ["address"],
            "test_web3",
            True,
        ),
        (
            WrappedxDaiContract().address,
            "balanceOf",
            ["uint256"],
            "test_web3",
            False,
        ),
        (
            sDaiContract().address,
            "balanceOf",
            ["address"],
            "test_web3",
            True,
        ),
        (
            sDaiContract().address,
            "deposit",
            ["uint256", "address"],
            "test_web3",
            True,
        ),
    ],
)
def test_contract_implements_function(
    contract_address: ChecksumAddress,
    function_name: str,
    function_arg_types: list[str],
    web3_fixture: str,
    expected: bool,
    request: pytest.FixtureRequest,
) -> None:
    web3 = request.getfixturevalue(web3_fixture)
    assert (
        contract_implements_function(
            contract_address, function_name, web3, function_arg_types
        )
        == expected
    )
