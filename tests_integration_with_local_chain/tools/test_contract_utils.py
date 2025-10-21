from web3 import Web3

from prediction_market_agent_tooling.tools.contract import (
    eip_1967_proxy_address,
    uni_implementation_address,
    zeppelinos_unstructured_storage_proxy_address,
)


def test_eip_1967_imp(
    local_web3: Web3,
) -> None:
    # EURe v2 to its imp address
    assert (
        eip_1967_proxy_address(
            Web3.to_checksum_address("0x420ca0f9b9b604ce0fd9c18ef134c705e5fa3430"),
            local_web3,
        )
        == "0x60cb9FdD0fcFd9BB3b2B721864Db5E7C07F4635D"
    )


def test_zeppelinos_imp(
    local_web3: Web3,
) -> None:
    assert (
        zeppelinos_unstructured_storage_proxy_address(
            Web3.to_checksum_address("0x3221a28ed2b2e955da64d1d299956f277562c95c"),
            local_web3,
        )
        == "0xF5C1c5E5215b9Bf2BC389F956a5B8D41605586C8"
    )


def test_uni_implementation_address(
    local_web3: Web3,
) -> None:
    assert "0xF5C1c5E5215b9Bf2BC389F956a5B8D41605586C8" in uni_implementation_address(
        Web3.to_checksum_address("0x3221a28ed2b2e955da64d1d299956f277562c95c"),
        local_web3,
    )
