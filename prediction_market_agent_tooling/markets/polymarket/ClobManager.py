from enum import Enum

from py_clob_client.client import ClobClient

from prediction_market_agent_tooling.chains import POLYGON_CHAIN_ID
from prediction_market_agent_tooling.config import APIKeys
from prediction_market_agent_tooling.gtypes import USD
from prediction_market_agent_tooling.tools.singleton import SingletonMeta

HOST = "https://clob.polymarket.com"


class PolymarketPriceSideEnum(str, Enum):
    BUY = "buy"
    SELL = "sell"


class ClobManager(metaclass=SingletonMeta):
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
