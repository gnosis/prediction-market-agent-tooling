# ToDo - move to env
#  - description: Gnosis Chain (Prod)
#     url: https://api.cow.fi/xdai
#   - description: Gnosis Chain (Staging)
#     url: https://barn.api.cow.fi/xdai
from enum import Enum

import requests
from eth_account import Account
from eth_account.signers.local import LocalAccount
from eth_typing import ChecksumAddress

from prediction_market_agent_tooling.gtypes import Wei
from prediction_market_agent_tooling.tools.cowswap.encoding import (
    MESSAGE_TYPES_CANCELLATION,
    DOMAIN,
    MESSAGE_TYPES,
)
from prediction_market_agent_tooling.tools.cowswap.models import (
    Quote,
    OrderStatus,
    OrderKind,
)


class CowServer(str, Enum):
    GNOSIS_PROD = "https://api.cow.fi/xdai"
    GNOSIS_STAGING = "https://barn.api.cow.fi/xdai"


class CowClient:
    def __init__(
        self, account: LocalAccount, api_url: CowServer = CowServer.GNOSIS_STAGING
    ):
        self.api_url = api_url
        self.account = account

    def get_version(self) -> str:
        r = requests.get(f"{self.api_url.value}/api/v1/version")
        return r.text

    def approve_spending_of_token(self) -> None:
        raise NotImplementedError()

    def build_swap_params(
        self, sell_token: ChecksumAddress, buy_token: ChecksumAddress, sell_amount: Wei
    ) -> Quote:
        quote = Quote(
            from_=self.account.address,
            sell_token=sell_token,
            buy_token=buy_token,
            receiver=self.account.address,
            sellAmountBeforeFee=str(sell_amount),
            kind=OrderKind.SELL,
            appData="0x0000000000000000000000000000000000000000000000000000000000000000",
            validFor=1080,
        )
        return quote

    def post_quote(self, quote: Quote) -> Quote:
        quote_dict = quote.dict(by_alias=True, exclude_none=True)
        r = requests.post(f"{self.api_url}/api/v1/quote", json=quote_dict)
        r.raise_for_status()
        return Quote.model_validate(r.json(["quote"]))

    def build_order_with_fee_and_sell_amounts(self, quote: Quote) -> dict:
        new_sell_amount = int(quote["sellAmount"]) + int(quote["feeAmount"])
        order_data = {
            **quote,
            "sellAmount": str(new_sell_amount),
            "feeAmount": "0",
        }
        return order_data

    def post_order(self, quote: Quote) -> str:
        # sign
        order_data = self.build_order_with_fee_and_sell_amounts(quote)
        signed_message = Account.sign_typed_data(
            self.account.key, DOMAIN, MESSAGE_TYPES, order_data
        )
        order_data["signature"] = signed_message.signature.hex()
        # post
        r = requests.post(f"{self.api_url}/api/v1/orders", json=order_data)
        r.raise_for_status()
        order_id = r.content.decode().replace('"', "")
        return order_id

    def cancel_order_if_not_already_cancelled(self, order_uids: list[str]) -> None:
        signed_message_cancellation = Account.sign_typed_data(
            self.account.key,
            DOMAIN,
            MESSAGE_TYPES_CANCELLATION,
            {"orderUids": order_uids},
        )
        cancellation_request_obj = {
            "orderUids": order_uids,
            "signature": signed_message_cancellation.signature.hex(),
            "signingScheme": "eip712",
        }

        order_status = self.get_order_status(order_uids[0])
        if order_status == OrderStatus.CANCELLED:
            return

        r = requests.delete(
            f"{self.api_url.value}/api/v1/orders", json=cancellation_request_obj
        )
        r.raise_for_status()

    def get_order_status(self, order_uid: str) -> OrderStatus:
        r = requests.get(f"{self.api_url.value}/api/v1/orders/{order_uid}")
        r.raise_for_status()

        order_type = r.json()["type"]
        if order_type not in iter(OrderStatus):
            raise ValueError(
                f"order_type {order_type} from order_uid {order_uid} cannot be processed."
            )
        return OrderStatus(order_type)
