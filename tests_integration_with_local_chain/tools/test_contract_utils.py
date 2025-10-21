from web3 import Web3

from prediction_market_agent_tooling.tools.contract import (
    eip_1967_proxy_address,
    zeppelinos_proxy_address,
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
    # EURe v2 to its imp address
    assert zeppelinos_proxy_address(
        Web3.to_checksum_address("0x3221a28ed2b2e955da64d1d299956f277562c95c"),
        local_web3,
    ) == Web3.to_checksum_address("0xf5c1c5e5215b9bf2bc389f956a5b8d41605586c8")
