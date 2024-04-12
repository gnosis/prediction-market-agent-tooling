from eth_account import Account
from gnosis.eth import EthereumClient
from gnosis.safe import Safe
from loguru import logger

from prediction_market_agent_tooling.deploy.safe.safe_manager import SafeManager
from prediction_market_agent_tooling.gtypes import PrivateKey
from web3 import Web3


def create_safe(
    from_private_key: PrivateKey,
    ethereum_client: EthereumClient | None = None,
) -> Safe:
    account = Account.from_key(from_private_key)
    s = SafeManager(ethereum_client, account, None)
    owners = [Web3.to_checksum_address(account.address)]
    if not ethereum_client:
        ethereum_client = EthereumClient()

    logger.debug(f"Deploying Safe for address {account.address}")
    m = s.deploy_safe(ethereum_client, account, account, owners, 1)
    logger.info(
        f"Deployed Safe with address {m.safe.address} and version {m.safe.get_version()}"
    )
    return m.safe
