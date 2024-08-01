from typing import Generator

import pytest

from prediction_market_agent_tooling.tools.cowswap.cow_client import (
    CowClient,
    CowServer,
)
from prediction_market_agent_tooling.tools.cowswap.models import (
    OrderCreation,
    Quote,
    OrderKind,
    AppData,
    CowMetadata,
)
from prediction_market_agent_tooling.tools.hexbytes_custom import HexBytes


@pytest.fixture(scope="module")
def test_mock_client() -> Generator[CowClient, None, None]:
    yield CowClient(api_url=CowServer.GNOSIS_PROD)


@pytest.fixture(scope="module")
def test_quote() -> Generator[Quote, None, None]:
    yield Quote(
        from_="0x6810e776880c02933d47db1b9fc05908e5386b96",
        sellToken="0xe91d153e0b41518a2ce8dd3d7944fa863463a97d",
        buyToken="0x2a22f9c3b484c3629090feed35f17ff8f88f76f0",
        receiver="0x6810e776880c02933d47db1b9fc05908e5386b96",
        sellAmountBeforeFee="2000000000000000000",
        buyAmountAfterFee="2000000000000000000",
        kind=OrderKind.BUY,
        appData=AppData(metadata=CowMetadata()).json(),
        validFor=1080,
    )
    # yield Quote.from_dict(
    #     {
    #         "sellToken": "0xe91D153E0b41518A2Ce8Dd3D7944Fa863463a97d",
    #         "buyToken": "0x6a023ccd1ff6f2045c3309768ead9e68f978f6e1",
    #         "receiver": "0x6810e776880c02933d47db1b9fc05908e5386b96",
    #         "appData": '{"version":"0.9.0","metadata":{}}',
    #         "appDataHash": "0xc990bae86208bfdfba8879b64ab68da5905e8bb97aa3da5c701ec1183317a6f6",
    #         "sellTokenBalance": "erc20",
    #         "buyTokenBalance": "erc20",
    #         "from": "0x6810e776880c02933d47db1b9fc05908e5386b96",
    #         "priceQuality": "verified",
    #         "signingScheme": "eip712",
    #         "onchainOrder": False,
    #         "kind": "buy",
    #         "buyAmountAfterFee": "1000000000000000000",
    #     }
    # )


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


def test_get_quote(test_mock_client: CowClient, test_quote: Quote) -> None:
    result = test_mock_client.post_quote(test_quote)
    assert result is not None
