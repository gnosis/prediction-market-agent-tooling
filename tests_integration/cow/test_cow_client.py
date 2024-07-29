from typing import Generator

import pytest

from prediction_market_agent_tooling.tools.cowswap.cow_client import CowClient
from prediction_market_agent_tooling.tools.cowswap.models import (
    OrderCreation,
    OrderQuoteRequest,
)
from prediction_market_agent_tooling.tools.hexbytes_custom import HexBytes


@pytest.fixture(scope="module")
def test_mock_client() -> Generator[CowClient, None, None]:
    yield CowClient()


@pytest.fixture(scope="module")
def test_quote() -> Generator[OrderQuoteRequest, None, None]:
    yield OrderQuoteRequest.from_dict(
        {
            "sellToken": "0x6810e776880c02933d47db1b9fc05908e5386b96",
            "buyToken": "0x6810e776880c02933d47db1b9fc05908e5386b96",
            "receiver": "0x6810e776880c02933d47db1b9fc05908e5386b96",
            "appData": '{"version":"0.9.0","metadata":{}}',
            "appDataHash": "0x0000000000000000000000000000000000000000000000000000000000000000",
            "sellTokenBalance": "erc20",
            "buyTokenBalance": "erc20",
            "from": "0x6810e776880c02933d47db1b9fc05908e5386b96",
            "priceQuality": "verified",
            "signingScheme": "eip712",
            "onchainOrder": False,
            "kind": "sell",
            "sellAmountBeforeFee": "1234567890",
            "sellAmountAfterFee": "1234567890",
            "buyAmountBeforeFee": "1234567890",
            "buyAmountAfterFee": "1234567890",
        }
    )


@pytest.fixture(scope="module")
def test_order() -> Generator[OrderCreation, None, None]:
    quote = OrderCreation.from_dict(
        {
            "sellToken": "0x6810e776880c02933d47db1b9fc05908e5386b96",
            "buyToken": "0x6810e776880c02933d47db1b9fc05908e5386b96",
            "receiver": "0x6810e776880c02933d47db1b9fc05908e5386b96",
            "sellAmount": "1234567890",
            "buyAmount": "1234567890",
            "validTo": 0,
            "feeAmount": "1234567890",
            "kind": "buy",
            "partiallyFillable": True,
            "sellTokenBalance": "erc20",
            "buyTokenBalance": "erc20",
            "signingScheme": "eip712",
            "signature": HexBytes(
                "0x0000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000"
            ),
            "from": "0x6810e776880c02933d47db1b9fc05908e5386b96",
            "quoteId": 0,
            "appData": '{"version":"0.9.0","metadata":{}}',
            "appDataHash": "0x0000000000000000000000000000000000000000000000000000000000000000",
        }
    )
    yield quote


def test_version(test_mock_client: CowClient) -> None:
    version = test_mock_client.get_version()
    assert version


def test_post_order(test_mock_client: CowClient, test_order: OrderCreation) -> None:
    posted_order_id = test_mock_client.post_order(test_order)
    status = test_mock_client.get_order_status(posted_order_id)
    assert status is not None


def test_get_quote(test_mock_client: CowClient, test_quote: OrderQuoteRequest) -> None:
    quote = test_mock_client.post_quote(test_quote)
    assert quote is not None
