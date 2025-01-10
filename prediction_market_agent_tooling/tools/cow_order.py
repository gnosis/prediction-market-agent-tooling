import asyncio

from cow_py.common.chains import Chain
from cow_py.common.config import SupportedChainId
from cow_py.common.constants import CowContractAddress
from cow_py.contracts.domain import domain
from cow_py.contracts.order import Order
from cow_py.contracts.sign import EcdsaSignature, SigningScheme
from cow_py.contracts.sign import sign_order as _sign_order
from cow_py.order_book.api import OrderBookApi
from cow_py.order_book.config import Envs, OrderBookAPIConfigFactory
from cow_py.order_book.generated.model import (
    UID,
    OrderCreation,
    OrderQuoteRequest,
    OrderQuoteResponse,
    OrderQuoteSide1,
    OrderQuoteSideKindSell,
    TokenAmount,
)
from eth_account.signers.local import LocalAccount
from pydantic import BaseModel
from web3 import Web3

from prediction_market_agent_tooling.config import APIKeys
from prediction_market_agent_tooling.gtypes import ChecksumAddress, xDai
from prediction_market_agent_tooling.tools.contract import ContractERC20OnGnosisChain
from prediction_market_agent_tooling.tools.web3_utils import xdai_to_wei

ZERO_APP_DATA = "0x0000000000000000000000000000000000000000000000000000000000000000"


class CompletedOrder(BaseModel):
    uid: UID
    url: str


def swap_tokens(
    amount: xDai,
    sell_token: ChecksumAddress,
    buy_token: ChecksumAddress,
    api_keys: APIKeys,
    chain: Chain = Chain.GNOSIS,
    app_data: str = ZERO_APP_DATA,
    env: Envs = "prod",
    web3: Web3 | None = None,
) -> CompletedOrder:
    # CoW library uses async, so we need to wrap the call in asyncio.run for us to use it.
    return asyncio.run(
        swap_tokens_async(
            amount, sell_token, buy_token, api_keys, chain, app_data, env, web3
        )
    )


async def swap_tokens_async(
    amount: xDai,
    sell_token: ChecksumAddress,
    buy_token: ChecksumAddress,
    api_keys: APIKeys,
    chain: Chain,
    app_data: str,
    env: Envs,
    web3: Web3 | None,
) -> CompletedOrder:
    account = api_keys.get_account()
    amount_wei = xdai_to_wei(amount)
    chain_id = SupportedChainId(chain.value[0])

    order_book_api = OrderBookApi(OrderBookAPIConfigFactory.get_config(env, chain_id))

    # Approve the CoW Swap Vault Relayer to get the sell token.
    ContractERC20OnGnosisChain(address=sell_token).approve(
        api_keys,
        Web3.to_checksum_address(CowContractAddress.VAULT_RELAYER.value),
        amount_wei=amount_wei,
        web3=web3,
    )

    order_quote_request = OrderQuoteRequest.model_validate(
        {
            "sellToken": sell_token,
            "buyToken": buy_token,
            "from": api_keys.bet_from_address,
        }
    )
    order_side = OrderQuoteSide1(
        kind=OrderQuoteSideKindSell.sell,
        sellAmountBeforeFee=TokenAmount(str(amount_wei)),
    )

    order_quote = await get_order_quote(order_quote_request, order_side, order_book_api)
    order = Order(
        sell_token=sell_token,
        buy_token=buy_token,
        receiver=api_keys.bet_from_address,
        valid_to=order_quote.quote.validTo,
        app_data=app_data,
        sell_amount=amount_wei,  # Since it is a sell order, the sellAmountBeforeFee is the same as the sellAmount.
        buy_amount=int(order_quote.quote.buyAmount.root),
        fee_amount=0,  # CoW Swap does not charge fees.
        kind=OrderQuoteSideKindSell.sell.value,
        sell_token_balance="erc20",
        buy_token_balance="erc20",
    )

    signature = sign_order(chain, account, order)
    order_uid = await post_order(api_keys, order, signature, order_book_api)
    order_link = order_book_api.get_order_link(order_uid)

    return CompletedOrder(uid=order_uid, url=order_link)


async def get_order_quote(
    order_quote_request: OrderQuoteRequest,
    order_side: OrderQuoteSide1,
    order_book_api: OrderBookApi,
) -> OrderQuoteResponse:
    return await order_book_api.post_quote(order_quote_request, order_side)


def sign_order(chain: Chain, account: LocalAccount, order: Order) -> EcdsaSignature:
    order_domain = domain(
        chain=chain, verifying_contract=CowContractAddress.SETTLEMENT_CONTRACT.value
    )

    return _sign_order(order_domain, order, account, SigningScheme.EIP712)


async def post_order(
    api_keys: APIKeys,
    order: Order,
    signature: EcdsaSignature,
    order_book_api: OrderBookApi,
) -> UID:
    order_creation = OrderCreation.model_validate(
        {
            "from": api_keys.bet_from_address,
            "sellToken": order.sellToken,
            "buyToken": order.buyToken,
            "sellAmount": str(order.sellAmount),
            "feeAmount": str(order.feeAmount),
            "buyAmount": str(order.buyAmount),
            "validTo": order.validTo,
            "kind": order.kind,
            "partiallyFillable": order.partiallyFillable,
            "appData": order.appData,
            "signature": signature.data,
            "signingScheme": "eip712",
            "receiver": order.receiver,
        }
    )
    return await order_book_api.post_order(order_creation)
