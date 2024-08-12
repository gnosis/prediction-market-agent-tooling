import pytest
from _pytest.fixtures import FixtureRequest
from web3 import Web3

from prediction_market_agent_tooling.gtypes import ChecksumAddress
from prediction_market_agent_tooling.markets.omen.omen_contracts import (
    WrappedxDaiContract,
    sDaiContract,
)
from prediction_market_agent_tooling.tools.contract import (
    ContractDepositableWrapperERC20BaseClass,
    ContractERC20BaseClass,
    ContractERC4626BaseClass,
    contract_implements_function,
    init_collateral_token_contract,
)


def test_init_erc4626_erc20_contract_return_erc4626_instance(local_web3: Web3) -> None:
    contract = init_collateral_token_contract(sDaiContract().address, local_web3)
    assert isinstance(
        contract, ContractERC4626BaseClass
    ), f"Returned contract is {type(contract)}"


def test_init_erc4626_erc20_contract_return_wrappererc20_instance(
    local_web3: Web3,
) -> None:
    contract = init_collateral_token_contract(WrappedxDaiContract().address, local_web3)
    assert isinstance(
        contract, ContractDepositableWrapperERC20BaseClass
    ), f"Returned contract is {type(contract)}"


def test_init_erc4626_erc20_contract_return_erc20_instance(local_web3: Web3) -> None:
    contract = init_collateral_token_contract(
        Web3.to_checksum_address("0x4ecaba5870353805a9f068101a40e0f32ed605c6"),
        local_web3,
    )
    assert isinstance(
        contract, ContractERC20BaseClass
    ), f"Returned contract is {type(contract)}"


def test_init_erc4626_erc20_contract_throws_on_unknown_contract(
    local_web3: Web3,
) -> None:
    with pytest.raises(ValueError) as e:
        init_collateral_token_contract(
            Web3.to_checksum_address("0x7d3A0DA18e14CCb63375cdC250E8A8399997816F"),
            local_web3,
        )
    assert "is neither Depositable ERC-20, ERC-20 nor ERC-4626" in str(e)


@pytest.mark.parametrize(
    "contract_address, function_name, function_arg_types, expected",
    [
        (
            WrappedxDaiContract().address,
            "balanceOf",
            ["address"],
            True,
        ),
        (
            WrappedxDaiContract().address,
            "balanceOf",
            ["uint256"],
            False,
        ),
        (
            sDaiContract().address,
            "balanceOf",
            ["address"],
            True,
        ),
        (
            sDaiContract().address,
            "deposit",
            ["uint256", "address"],
            True,
        ),
    ],
)
def test_contract_implements_function(
    contract_address: ChecksumAddress,
    function_name: str,
    function_arg_types: list[str],
    expected: bool,
    request: FixtureRequest,
) -> None:
    web3 = request.getfixturevalue("local_web3")
    assert (
        contract_implements_function(
            contract_address, function_name, web3, function_arg_types
        )
        == expected
    )
