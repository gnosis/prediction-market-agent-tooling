import secrets

from eth_account.signers.local import LocalAccount
from eth_typing import ChecksumAddress
from gnosis.eth import EthereumClient
from gnosis.eth.constants import NULL_ADDRESS
from gnosis.eth.contracts import get_safe_V1_4_1_contract
from gnosis.safe import Safe, ProxyFactory
from loguru import logger
from safe_cli.safe_addresses import (
    get_safe_contract_address,
    get_safe_l2_contract_address,
    get_proxy_factory_address,
    get_default_fallback_handler_address,
)

from prediction_market_agent_tooling.tools.hexbytes_custom import HexBytes


def create_safe(
    ethereum_client: EthereumClient,
    account: LocalAccount,
    owners: list[str],
    salt_nonce: int,
    threshold=1,
    without_events=False,  # following safe-cli convention
) -> ChecksumAddress | None:
    to = NULL_ADDRESS
    data = b""
    payment_token = NULL_ADDRESS
    payment = 0
    payment_receiver = NULL_ADDRESS

    if len(owners) < threshold:
        raise ValueError("Threshold cannot be bigger than the number of unique owners")

    ethereum_network = ethereum_client.get_network()

    safe_contract_address = (
        get_safe_contract_address(ethereum_client)
        if without_events
        else get_safe_l2_contract_address(ethereum_client)
    )
    proxy_factory_address = get_proxy_factory_address(ethereum_client)
    fallback_handler = get_default_fallback_handler_address(ethereum_client)

    if not ethereum_client.is_contract(safe_contract_address):
        raise EnvironmentError(
            f"Safe contract address {safe_contract_address} "
            f"does not exist on network {ethereum_network.name}"
        )
    elif not ethereum_client.is_contract(proxy_factory_address):
        raise EnvironmentError(
            f"Proxy contract address {proxy_factory_address} "
            f"does not exist on network {ethereum_network.name}"
        )
    elif fallback_handler != NULL_ADDRESS and not ethereum_client.is_contract(
        fallback_handler
    ):
        raise EnvironmentError(
            f"Fallback handler address {fallback_handler} "
            f"does not exist on network {ethereum_network.name}"
        )

    account_balance: int = ethereum_client.get_balance(account.address)
    if not account_balance:
        logger.info(
            "Client does not have any funds. Let's try anyway in case it's a network without gas costs"
        )
    else:
        ether_account_balance = round(
            ethereum_client.w3.from_wei(account_balance, "ether"), 6
        )
        logger.info(
            f"Network {ethereum_client.get_network().name} - Sender {account.address} - "
            f"Balance: {ether_account_balance} xDAI"
        )

    if not ethereum_client.w3.eth.get_code(
        safe_contract_address
    ) or not ethereum_client.w3.eth.get_code(proxy_factory_address):
        raise EnvironmentError("Network not supported")

    logger.info(
        f"Creating new Safe with owners={owners} threshold={threshold} salt-nonce={salt_nonce}"
    )
    safe_version = Safe(safe_contract_address, ethereum_client).retrieve_version()
    logger.info(
        f"Safe-master-copy={safe_contract_address} version={safe_version}\n"
        f"Fallback-handler={fallback_handler}\n"
        f"Proxy factory={proxy_factory_address}"
    )

    safe_contract = get_safe_V1_4_1_contract(ethereum_client.w3, safe_contract_address)
    safe_creation_tx_data = HexBytes(
        safe_contract.functions.setup(
            owners,
            threshold,
            to,
            data,
            fallback_handler,
            payment_token,
            payment,
            payment_receiver,
        ).build_transaction({"gas": 1, "gasPrice": 1})["data"]
    )

    proxy_factory = ProxyFactory(proxy_factory_address, ethereum_client)
    expected_safe_address = proxy_factory.calculate_proxy_address(
        safe_contract_address, safe_creation_tx_data, salt_nonce
    )
    if ethereum_client.is_contract(expected_safe_address):
        logger.info(f"Safe on {expected_safe_address} is already deployed")
        return expected_safe_address

    ethereum_tx_sent = proxy_factory.deploy_proxy_contract_with_nonce(
        account, safe_contract_address, safe_creation_tx_data, salt_nonce
    )
    logger.info(
        f"Sent tx with tx-hash={ethereum_tx_sent.tx_hash.hex()} "
        f"Safe={ethereum_tx_sent.contract_address} is being created"
    )
    logger.info(f"Tx parameters={ethereum_tx_sent.tx}")
    return ethereum_tx_sent.contract_address
