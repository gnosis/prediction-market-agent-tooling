# ToDo - move to env
#  - description: Gnosis Chain (Prod)
#     url: https://api.cow.fi/xdai
#   - description: Gnosis Chain (Staging)
#     url: https://barn.api.cow.fi/xdai
from enum import Enum

import requests

from prediction_market_agent_tooling.tools.cowswap.models import (
    OrderCreation,
    OrderQuoteRequest,
)


class CowServer(str, Enum):
    GNOSIS_PROD = "https://api.cow.fi/xdai"
    GNOSIS_STAGING = "https://barn.api.cow.fi/xdai"


class CowClient:
    def __init__(self, api_url: CowServer = CowServer.GNOSIS_STAGING):
        self.api_url = api_url

    def get_version(self) -> str:
        r = requests.get(f"{self.api_url.value}/api/v1/version")
        return r.text

    def post_quote(self, quote: OrderQuoteRequest):
        r = requests.post(
            f"{self.api_url.value}/api/v1/quote", json=quote.model_dump_json()
        )
        print(r.content)
        r.raise_for_status()

    def post_order(self, order: OrderCreation):
        r = requests.post(
            f"{self.api_url.value}/api/v1/orders", json=order.model_dump_json()
        )
        # Example from test_cow_client does not work (same as API example from docs)
        # https://docs.cow.fi/cow-protocol/reference/apis/orderbook
        print(r.content)
        # Failure -  [100%]b'Request body deserialize error: invalid type: string "{\\"sell_token\\":\\"0x6810e776880c02933d47db1b9fc05908e5386b96\\",\\"buy_token\\":\\"0x6810e776880c02933d47db1b9fc05908e5386b96\\",\\"receiver\\":\\"0x6810e776880c02933d47db1b9fc05908e5386b96\\",\\"sell_amount\\":\\"1234567890\\",\\"buy_amount\\":\\"1234567890\\",\\"valid_to\\":0,\\"fee_amount\\":\\"1234567890\\",\\"kind\\":\\"buy\\",\\"partially_fillable\\":true,\\"sell_token_balance\\":\\"erc20\\",\\"buy_token_balance\\":\\"erc20\\",\\"signing_scheme\\":\\"eip712\\",\\"signature\\":\\"0x0000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000\\",\\"var_from\\":\\"0x6810e776880c02933d47db1b9fc05908e5386b96\\",\\"quote_id\\":0,\\"app_data\\":{\\"anyof_schema_1_validator\\":\\"{\\\\\\"version\\\\\\":\\\\\\"0.9.0\\\\\\",\\\\\\"metadata\\\\\\":{}}\\",\\"anyof_schema_2_validator\\":null,\\"actual_instance\\":\\"{\\\\\\"version\\\\\\":\\\\\\"0.9.0\\\\\\",\\\\\\"metadata\\\\\\":{}}\\",\\"any_of_schemas\\":[\\"str\\"]},\\"app_data_hash\\":\\"0x0000000000000000000000000000000000000000000000000000000000000000\\"}", expected struct OrderCreation at line 1 column 986'
        r.raise_for_status()
        return r.json()

    def get_order_status(self):
        pass
