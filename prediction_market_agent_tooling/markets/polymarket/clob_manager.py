from enum import Enum
from threading import Lock
from typing import Any, Dict, Type, TypeVar

from py_clob_client.client import ClobClient
from py_clob_client.clob_types import (
    MarketOrderArgs,
    OrderType,
)
from py_clob_client.order_builder.constants import BUY, SELL
from pydantic import BaseModel
from web3 import Web3
from web3.middleware import ExtraDataToPOAMiddleware

from prediction_market_agent_tooling.chains import POLYGON_CHAIN_ID
from prediction_market_agent_tooling.config import APIKeys, RPCConfig
from prediction_market_agent_tooling.gtypes import USD, Wei, HexBytes
from prediction_market_agent_tooling.markets.polymarket.constants import (
    CTF_EXCHANGE_POLYMARKET,
    NEG_RISK_EXCHANGE,
    NEG_RISK_ADAPTER,
    POLYMARKET_TINY_BET_AMOUNT,
)
from prediction_market_agent_tooling.markets.polymarket.polymarket_contracts import (
    USDCContract,
    PolymarketConditionalTokenContract,
)
from prediction_market_agent_tooling.tools.cow.cow_order import handle_allowance

HOST = "https://clob.polymarket.com"


class AllowanceResult(BaseModel):
    balance: float
    allowances: Dict[str, float]


class PolymarketPriceSideEnum(str, Enum):
    BUY = "BUY"
    SELL = "SELL"


class OrderStatusEnum(str, Enum):
    MATCHED = "matched"
    LIVE = "live"
    DELAYED = "delayed"
    UNMATCHED = "unmatched"


class CreateOrderResult(BaseModel):
    errorMsg: str
    orderID: str
    transactionsHashes: list[HexBytes]
    status: OrderStatusEnum
    success: bool


T = TypeVar("T", bound="ClobManager")


class ClobManagerMeta(type):
    """Singleton metaclass, one instance per API key's private key."""

    _instances: Dict[str, "ClobManager"] = {}
    _lock: Lock = Lock()

    def __call__(cls: Type[T], api_keys: APIKeys, *args: Any, **kwargs: Any) -> T:
        # Use the API key as the unique identifier for each instance
        key = api_keys.bet_from_private_key.get_secret_value()
        if key not in cls._instances:
            with cls._lock:
                if key not in cls._instances:
                    instance = super().__call__(api_keys, *args, **kwargs)
                    cls._instances[key] = instance
        return cls._instances[key]


class ClobManager(metaclass=ClobManagerMeta):
    def __init__(self, api_keys: APIKeys):
        ### Initialization of a client that trades directly from an EOA.
        self.api_keys = api_keys
        self.clob_client = ClobClient(
            HOST,
            key=api_keys.bet_from_private_key.get_secret_value(),
            chain_id=POLYGON_CHAIN_ID,
        )
        self.clob_client.set_api_creds(self.clob_client.create_or_derive_api_creds())
        self.polygon_web3 = Web3(Web3.HTTPProvider(RPCConfig().polygon_rpc_url))
        self.polygon_web3.middleware_onion.inject(ExtraDataToPOAMiddleware, layer=0)
        self.__init_approvals(polygon_web3=self.polygon_web3)

    def get_token_price(self, token_id: int, side: PolymarketPriceSideEnum) -> USD:
        price_data = self.clob_client.get_price(token_id=token_id, side=side.value)
        return USD(float(price_data["price"]))

    def place_buy_market_order(
        self, token_id: int, usdc_amount: float
    ) -> CreateOrderResult:
        if usdc_amount < 1.0:
            raise ValueError(
                f"usdc_amounts < 1.0 are not supported by Polymarket, got {usdc_amount}"
            )

        # create a market buy order for the equivalent of `usdc_amount` USDC at the market price
        order_args = MarketOrderArgs(
            token_id=str(token_id),
            amount=usdc_amount,  # USD
            side=BUY,
        )

        signed_order = self.clob_client.create_market_order(order_args)
        resp = self.clob_client.post_order(signed_order, orderType=OrderType.FOK)
        resp_model = CreateOrderResult.model_validate(resp)
        return resp_model

    def place_sell_market_order(self, token_id: int, token_shares: float) -> str:
        # create a market buy order for the equivalent of 100 USDC at the market price
        order_args = MarketOrderArgs(
            token_id=str(token_id),
            amount=token_shares,  # SHARES
            side=SELL,
        )
        signed_order = self.clob_client.create_market_order(order_args)
        resp = self.clob_client.post_order(signed_order, orderType=OrderType.FOK)
        return resp

    def __init_approvals(
        self,
        polygon_web3: Web3 | None = None,
    ) -> None:
        # from https://github.com/Polymarket/agents/blob/main/agents/polymarket/polymarket.py#L341
        polygon_web3 = polygon_web3 or self.polygon_web3

        usdc = USDCContract()

        # When setting allowances on Polymarket, it's important to set a large amount, because
        # every trade reduces the allowance by the amount of the trade.
        large_amount_wei = Wei(int(100 * 1e6))  # 100 USDC in Wei
        amount_to_check_wei = Wei(POLYMARKET_TINY_BET_AMOUNT.value * 1e6)
        ctf = PolymarketConditionalTokenContract()

        for target_address in [
            CTF_EXCHANGE_POLYMARKET,
            NEG_RISK_EXCHANGE,
            NEG_RISK_ADAPTER,
        ]:
            handle_allowance(
                api_keys=self.api_keys,
                sell_token=usdc.address,
                for_address=target_address,
                amount_to_check_wei=amount_to_check_wei,
                amount_to_set_wei=large_amount_wei,
                web3=polygon_web3,
            )

            ctf.approve_if_not_approved(
                api_keys=self.api_keys,
                for_address=target_address,
                web3=polygon_web3,
            )
