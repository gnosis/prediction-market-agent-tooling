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
    USDCeContract,
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


class PriceResponse(BaseModel):
    price: float


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
        self.api_keys = api_keys
        self.clob_client = ClobClient(
            HOST,
            key=api_keys.bet_from_private_key.get_secret_value(),
            chain_id=POLYGON_CHAIN_ID,
        )
        self.clob_client.set_api_creds(self.clob_client.create_or_derive_api_creds())
        self.polygon_web3 = RPCConfig().get_polygon_web3()
        self.__init_approvals(polygon_web3=self.polygon_web3)

    def get_token_price(self, token_id: int, side: PolymarketPriceSideEnum) -> USD:
        price_data = self.clob_client.get_price(token_id=token_id, side=side.value)
        price_item = PriceResponse.model_validate(price_data)
        return USD(price_item.price)

    def _place_market_order(
        self, token_id: int, amount: float, side: PolymarketPriceSideEnum
    ) -> CreateOrderResult:
        """Internal method to place a market order.

        Args:
            token_id: The token ID to trade
            amount: The amount to trade (USDC for BUY, token shares for SELL)
            side: Either BUY or SELL

        Returns:
            CreateOrderResult: The result of the order placement

        Raises:
            ValueError: If usdc_amount is < 1.0 for BUY orders
        """
        if side == PolymarketPriceSideEnum.BUY and amount < 1.0:
            raise ValueError(
                f"usdc_amounts < 1.0 are not supported by Polymarket, got {amount}"
            )

        order_args = MarketOrderArgs(
            token_id=str(token_id),
            amount=amount,
            side=side.value,
        )

        signed_order = self.clob_client.create_market_order(order_args)
        resp = self.clob_client.post_order(signed_order, orderType=OrderType.FOK)
        return CreateOrderResult.model_validate(resp)

    def place_buy_market_order(
        self, token_id: int, usdc_amount: float
    ) -> CreateOrderResult:
        """Place a market buy order for the given token with the specified USDC amount."""
        return self._place_market_order(token_id, usdc_amount, BUY)

    def place_sell_market_order(
        self, token_id: int, token_shares: float
    ) -> CreateOrderResult:
        """Place a market sell order for the given token with the specified number of shares."""
        return self._place_market_order(token_id, token_shares, SELL)

    def __init_approvals(
        self,
        polygon_web3: Web3 | None = None,
    ) -> None:
        # from https://github.com/Polymarket/agents/blob/main/agents/polymarket/polymarket.py#L341
        polygon_web3 = polygon_web3 or self.polygon_web3

        usdc = USDCeContract()

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
