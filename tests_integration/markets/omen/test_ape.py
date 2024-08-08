import pytest
from ape.managers import NetworkManager


@pytest.fixture
def whale(accounts):
    account = accounts[0]
    account.balance = "1000 ETH"  # This calls `anvil_setBalance` under-the-hood.
    return account


def test_dummy(networks: NetworkManager):
    print("accounts", networks)
    with networks.gnosis.mainnet_fork.use_provider("foundry") as provider:
        print(provider.name)

    # print(networks.provider.getBalance(whale.address))

    assert True
