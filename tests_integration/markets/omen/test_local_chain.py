def test_connect_local_chain(local_web3) -> None:
    assert local_web3.is_connected()
