import time

import pytest
from ape_test import TestAccount
from web3 import Web3

from prediction_market_agent_tooling.config import APIKeys
from prediction_market_agent_tooling.gtypes import (
    ChecksumAddress,
    CollateralToken,
    private_key_type,
    xDai,
    xdai_type,
)
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
    request: pytest.FixtureRequest,
) -> None:
    web3 = request.getfixturevalue("local_web3")
    assert (
        contract_implements_function(
            contract_address, function_name, web3, function_arg_types
        )
        == expected
    )


@pytest.mark.skip(
    reason="See https://github.com/gnosis/prediction-market-agent-tooling/issues/625"
)
def test_wont_retry(local_web3: Web3, accounts: list[TestAccount]) -> None:
    value = CollateralToken(10).as_wei
    from_account = accounts[0]
    to_account = accounts[1]

    start_time = time.time()
    with pytest.raises(Exception) as e:
        WrappedxDaiContract().transferFrom(
            api_keys=APIKeys(
                BET_FROM_PRIVATE_KEY=private_key_type(from_account.private_key)
            ),
            sender=Web3.to_checksum_address(from_account.address),
            recipient=Web3.to_checksum_address(to_account.address),
            amount_wei=value,
            web3=local_web3,
        )
    end_time = time.time()

    assert "reverted" in str(e)
    assert (
        end_time - start_time < 1
    ), "Should not retry --> should take less then 1 second to execute."


def test_sdai_asset_balance_of(local_web3: Web3) -> None:
    assert (
        sDaiContract().get_asset_token_balance(
            Web3.to_checksum_address("0x7d3A0DA18e14CCb63375cdC250E8A8399997816F"),
            web3=local_web3,
        )
        >= 0
    )


def test_sdai_allowance_and_approval(
    local_web3: Web3, test_keys: APIKeys, accounts: list[TestAccount]
) -> None:
    amount_wei = xdai_to_wei(xdai_type(1))
    for_address = accounts[-1].address
    token_contract = sDaiContract()
    token_contract.approve(
        api_keys=test_keys,
        amount_wei=amount_wei,
        for_address=for_address,
        web3=local_web3,
    )
    allowance = token_contract.allowance(
        owner=test_keys.public_key, for_address=for_address, web3=local_web3
    )
    assert amount_wei == allowance
