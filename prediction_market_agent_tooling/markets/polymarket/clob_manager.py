from enum import Enum
from threading import Lock
from typing import Dict, Type, TypeVar, Any

from py_clob_client.client import ClobClient
from py_clob_client.clob_types import MarketOrderArgs, OrderType
from py_clob_client.order_builder.constants import BUY, SELL

from prediction_market_agent_tooling.chains import POLYGON_CHAIN_ID
from prediction_market_agent_tooling.config import APIKeys
from prediction_market_agent_tooling.gtypes import USD

HOST = "https://clob.polymarket.com"


class PolymarketPriceSideEnum(str, Enum):
    BUY = "buy"
    SELL = "sell"


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
        self.clob_client = ClobClient(
            HOST,
            key=api_keys.bet_from_private_key.get_secret_value(),
            chain_id=POLYGON_CHAIN_ID,
        )
        self.clob_client.set_api_creds(self.clob_client.create_or_derive_api_creds())

    def get_token_price(self, token_id: int, side: PolymarketPriceSideEnum) -> USD:
        price_data = self.clob_client.get_price(token_id=token_id, side=side.value)
        return USD(float(price_data["price"]))

    def place_buy_market_order(self, token_id: int, usdc_amount: float) -> str:
        # create a market buy order for the equivalent of `usdc_amount` USDC at the market price
        order_args = MarketOrderArgs(
            token_id=str(token_id),
            amount=usdc_amount,  # USD
            side=BUY,
        )
        signed_order = self.clob_client.create_market_order(order_args)
        resp = self.clob_client.post_order(signed_order, orderType=OrderType.FOK)
        return resp

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
