from ape.managers import NetworkManager


def test_dummy(networks: NetworkManager):
    print("accounts", networks)
    with networks.gnosis.mainnet.use_provider("alchemy") as alchemy:
        print(alchemy.name)
    assert True
