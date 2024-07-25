import pytest
from web3 import Web3

from prediction_market_agent_tooling.gtypes import ChecksumAddress
from prediction_market_agent_tooling.markets.omen.omen_contracts import (
    WrappedxDaiContract,
    sDaiContract,
)
from prediction_market_agent_tooling.tools.contract import (
    ContractDepositableWrapperERC20OnGnosisChain,
    ContractERC20OnGnosisChain,
    ContractERC4626OnGnosisChain,
    contract_implements_function,
    init_erc4626_or_wrappererc20_or_erc20_contract,
)


def test_init_erc4626_erc20_contract_return_erc4626_instance() -> None:
    contract = init_erc4626_or_wrappererc20_or_erc20_contract(sDaiContract().address)
    assert isinstance(
        contract, ContractERC4626OnGnosisChain
    ), f"Returned contract is {type(contract)}"


def test_init_erc4626_erc20_contract_return_wrappererc20_instance() -> None:
    contract = init_erc4626_or_wrappererc20_or_erc20_contract(
        WrappedxDaiContract().address
    )
    assert isinstance(
        contract, ContractDepositableWrapperERC20OnGnosisChain
    ), f"Returned contract is {type(contract)}"


def test_init_erc4626_erc20_contract_return_erc20_instance() -> None:
    contract = init_erc4626_or_wrappererc20_or_erc20_contract(
        Web3.to_checksum_address("0x4ecaba5870353805a9f068101a40e0f32ed605c6")
    )
    assert isinstance(
        contract, ContractERC20OnGnosisChain
    ), f"Returned contract is {type(contract)}"


def test_init_erc4626_erc20_contract_throws_on_unknown_contract() -> None:
    with pytest.raises(ValueError) as e:
        init_erc4626_or_wrappererc20_or_erc20_contract(
            Web3.to_checksum_address("0x7d3A0DA18e14CCb63375cdC250E8A8399997816F")
        )
    assert "is neither WrapperERC-20, ERC-20 nor ERC-4626" in str(e)


@pytest.mark.parametrize(
    "contract_address, function_name, function_arg_types, web3, expected",
    [
        (
            WrappedxDaiContract().address,
            "balanceOf",
            ["address"],
            WrappedxDaiContract().get_web3(),
            True,
        ),
        (
            WrappedxDaiContract().address,
            "balanceOf",
            ["uint256"],
            WrappedxDaiContract().get_web3(),
            False,
        ),
        (
            sDaiContract().address,
            "balanceOf",
            ["address"],
            sDaiContract().get_web3(),
            True,
        ),
        (
            sDaiContract().address,
            "deposit",
            ["uint256", "address"],
            sDaiContract().get_web3(),
            True,
        ),
    ],
)
def test_contract_implements_function(
    contract_address: ChecksumAddress,
    function_name: str,
    function_arg_types: list[str],
    web3: Web3,
    expected: bool,
) -> None:
    assert (
        contract_implements_function(
            contract_address, function_name, web3, function_arg_types
        )
        == expected
    )
