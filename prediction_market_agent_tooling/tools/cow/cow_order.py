import asyncio
from datetime import timedelta

import httpx
import tenacity
from cowdao_cowpy import swap_tokens
from cowdao_cowpy.common.api.errors import UnexpectedResponseError
from cowdao_cowpy.common.chains import Chain
from cowdao_cowpy.common.config import SupportedChainId
from cowdao_cowpy.common.constants import CowContractAddress
from cowdao_cowpy.cow.swap import get_order_quote
from cowdao_cowpy.order_book.api import OrderBookApi
from cowdao_cowpy.order_book.config import Envs, OrderBookAPIConfigFactory
from cowdao_cowpy.order_book.generated.model import (
    Address,
    OrderMetaData,
    OrderQuoteRequest,
    OrderQuoteSide1,
    OrderQuoteSideKindSell,
    OrderStatus,
    TokenAmount,
    OrderQuoteResponse,
    OrderQuoteSide3,
    OrderQuoteSideKindBuy,
)
from eth_account.signers.local import LocalAccount
from tenacity import stop_after_attempt, wait_fixed, retry_if_not_exception_type
from web3 import Web3

from prediction_market_agent_tooling.config import APIKeys
from prediction_market_agent_tooling.gtypes import ChecksumAddress, Wei
from prediction_market_agent_tooling.loggers import logger
from prediction_market_agent_tooling.tools.contract import ContractERC20OnGnosisChain
from prediction_market_agent_tooling.tools.utils import utcnow


class OrderStatusError(Exception):
    pass


class NoLiquidityAvailableOnCowException(Exception):
    """Custom exception for handling case where no liquidity available."""


def get_order_book_api(env: Envs, chain: Chain) -> OrderBookApi:
    chain_id = SupportedChainId(chain.value[0])
    return OrderBookApi(OrderBookAPIConfigFactory.get_config(env, chain_id))


@tenacity.retry(
    stop=tenacity.stop_after_attempt(3),
    wait=tenacity.wait_fixed(1),
    after=lambda x: logger.debug(f"get_sell_token_amount failed, {x.attempt_number=}."),
)
def get_sell_token_amount(
    buy_amount: Wei,
    sell_token: ChecksumAddress,
    buy_token: ChecksumAddress,
    chain: Chain = Chain.GNOSIS,
    env: Envs = "prod",
) -> Wei:
    """
    Calculate how much of the sell_token is needed to obtain a specified amount of buy_token.
    """
    order_book_api = get_order_book_api(env, chain)
    order_quote_request = OrderQuoteRequest(
        sellToken=Address(sell_token),
        buyToken=Address(buy_token),
        from_=Address(
            "0x1234567890abcdef1234567890abcdef12345678"
        ),  # Just random address, doesn't matter.
    )
    order_side = OrderQuoteSide3(
        kind=OrderQuoteSideKindBuy.buy,
        buyAmountAfterFee=TokenAmount(str(buy_amount)),
    )
    order_quote = asyncio.run(
        order_book_api.post_quote(order_quote_request, order_side)
    )
    return Wei(order_quote.quote.sellAmount.root)


@tenacity.retry(
    stop=stop_after_attempt(3),
    wait=wait_fixed(1),
    retry=retry_if_not_exception_type(NoLiquidityAvailableOnCowException),
)
def get_quote(
    amount_wei: Wei,
    sell_token: ChecksumAddress,
    buy_token: ChecksumAddress,
    chain: Chain = Chain.GNOSIS,
    env: Envs = "prod",
) -> OrderQuoteResponse:
    order_book_api = get_order_book_api(env, chain)
    order_quote_request = OrderQuoteRequest(
        sellToken=Address(sell_token),
        buyToken=Address(buy_token),
        from_=Address(
            "0x1234567890abcdef1234567890abcdef12345678"
        ),  # Just random address, doesn't matter.
    )
    order_side = OrderQuoteSide1(
        kind=OrderQuoteSideKindSell.sell,
        sellAmountBeforeFee=TokenAmount(str(amount_wei)),
    )

    try:
        order_quote = asyncio.run(
            get_order_quote(
                order_quote_request=order_quote_request,
                order_side=order_side,
                order_book_api=order_book_api,
            )
        )

        return order_quote

    except UnexpectedResponseError as e1:
        if "NoLiquidity" in e1.message:
            raise NoLiquidityAvailableOnCowException(e1.message)
        logger.warning(f"Found unexpected Cow response error: {e1}")
        raise
    except Exception as e:
        logger.warning(f"Found unhandled Cow response error: {e}")
        raise


def get_buy_token_amount_else_raise(
    amount_wei: Wei,
    sell_token: ChecksumAddress,
    buy_token: ChecksumAddress,
    chain: Chain = Chain.GNOSIS,
    env: Envs = "prod",
) -> Wei:
    order_quote = get_quote(
        amount_wei=amount_wei,
        sell_token=sell_token,
        buy_token=buy_token,
        chain=chain,
        env=env,
    )
    return Wei(order_quote.quote.buyAmount.root)


def swap_tokens_waiting(
    amount_wei: Wei,
    sell_token: ChecksumAddress,
    buy_token: ChecksumAddress,
    api_keys: APIKeys,
    chain: Chain = Chain.GNOSIS,
    env: Envs = "prod",
    web3: Web3 | None = None,
) -> OrderMetaData:
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
        amount=amount_wei.value,
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

        if order_metadata.status == OrderStatus.fulfilled:
            logger.info(f"Order {order.uid} ({order.url}) completed.")
            return order_metadata

        elif order_metadata.status in (
            OrderStatus.cancelled,
            OrderStatus.expired,
        ):
            raise ValueError(f"Order {order.uid} failed. {order.url}")

        if utcnow() - start_time > timeout:
            raise TimeoutError(
                f"Timeout waiting for order {order.uid} to be completed. {order.url}"
            )

        logger.info(
            f"Order status of {order.uid} ({order.url}): {order_metadata.status}, waiting..."
        )

        await asyncio.sleep(3.14)
