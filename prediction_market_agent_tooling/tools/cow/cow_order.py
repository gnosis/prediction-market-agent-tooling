import asyncio
from datetime import timedelta

import httpx
from cow_py import swap_tokens
from cow_py.common.chains import Chain
from cow_py.common.constants import CowContractAddress
from cow_py.order_book.config import Envs
from cow_py.order_book.generated.model import OrderMetaData, OrderStatus
from eth_account.signers.local import LocalAccount
from web3 import Web3

from prediction_market_agent_tooling.config import APIKeys
from prediction_market_agent_tooling.gtypes import ChecksumAddress, Wei, xDai
from prediction_market_agent_tooling.loggers import logger
from prediction_market_agent_tooling.tools.contract import ContractERC20OnGnosisChain
from prediction_market_agent_tooling.tools.utils import utcnow
from prediction_market_agent_tooling.tools.web3_utils import xdai_to_wei


def swap_tokens_waiting(
    amount: xDai,
    sell_token: ChecksumAddress,
    buy_token: ChecksumAddress,
    api_keys: APIKeys,
    chain: Chain = Chain.GNOSIS,
    env: Envs = "prod",
    web3: Web3 | None = None,
) -> OrderMetaData:
    amount_wei = xdai_to_wei(amount)
    account = api_keys.get_account()

    # Approve the CoW Swap Vault Relayer to get the sell token.
    ContractERC20OnGnosisChain(address=sell_token).approve(
        api_keys,
        Web3.to_checksum_address(CowContractAddress.VAULT_RELAYER.value),
        amount_wei=amount_wei,
        web3=web3,
    )

    # CoW library uses async, so we need to wrap the call in asyncio.run for us to use it.
    return asyncio.run(
        swap_tokens_waiting_async(
            amount_wei, sell_token, buy_token, account, chain, env
        )
    )


async def swap_tokens_waiting_async(
    amount_wei: Wei,
    sell_token: ChecksumAddress,
    buy_token: ChecksumAddress,
    account: LocalAccount,
    chain: Chain,
    env: Envs,
    timeout: timedelta = timedelta(seconds=60),
) -> OrderMetaData:
    order = await swap_tokens(
        amount=amount_wei,
        sell_token=sell_token,
        buy_token=buy_token,
        account=account,
        chain=chain,
        env=env,
    )
    logger.info(f"Order created: {order}")
    start_time = utcnow()

    while True:
        async with httpx.AsyncClient() as client:
            response = await client.get(order.url)
            order_metadata = OrderMetaData.model_validate(response.json())

        if order_metadata.status in (
            OrderStatus.fulfilled,
            OrderStatus.cancelled,
            OrderStatus.expired,
        ):
            return order_metadata

        if utcnow() - start_time > timeout:
            raise TimeoutError("Timeout waiting for order to be completed.")

        await asyncio.sleep(3.14)
