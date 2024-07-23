import pytest
from web3 import Web3

from prediction_market_agent_tooling.markets.omen.omen_contracts import (
    WrappedxDaiContract,
    sDaiContract,
)
from prediction_market_agent_tooling.tools.contract import (
    ContractERC20BaseClass,
    ContractERC4626BaseClass,
    init_erc4626_or_erc20_contract,
)


def test_init_erc4626_erc20_contract_return_erc4626_instance() -> None:
    contract = init_erc4626_or_erc20_contract(sDaiContract().address)
    assert isinstance(contract, ContractERC4626BaseClass)


def test_init_erc4626_erc20_contract_return_erc20_instance() -> None:
    contract = init_erc4626_or_erc20_contract(WrappedxDaiContract().address)
    assert isinstance(contract, ContractERC20BaseClass)


def test_init_erc4626_erc20_contract_throws_on_unknown_contract() -> None:
    with pytest.raises(ValueError) as e:
        init_erc4626_or_erc20_contract(
            Web3.to_checksum_address("0x7d3A0DA18e14CCb63375cdC250E8A8399997816F")
        )
    assert "is neither ERC-20 nor ERC-4626" in str(e)
