from typing import Generator
from unittest.mock import Mock, patch

import pytest
from eth_account.signers.local import LocalAccount
from web3 import Web3

from prediction_market_agent_tooling.tools.cowswap.cow_client import (
    CowClient,
    CowServer,
)
from prediction_market_agent_tooling.tools.cowswap.models import (
    OrderKind,
    QuoteInput,
    QuoteOutput,
    OrderStatus,
)

wxDAI = Web3.to_checksum_address("0xe91d153e0b41518a2ce8dd3d7944fa863463a97d")
COW = Web3.to_checksum_address("0x177127622c4A00F3d409B75571e12cB3c8973d3c")


@pytest.fixture(scope="module")
def test_mock_client(
    cowswap_test_account: LocalAccount,
) -> Generator[CowClient, None, None]:
    yield CowClient(api_url=CowServer.GNOSIS_PROD, account=cowswap_test_account)


@pytest.fixture(scope="module")
def test_quote(cowswap_test_account: LocalAccount) -> Generator[QuoteInput, None, None]:
    yield QuoteInput(
        from_=cowswap_test_account.address,
        sell_token=wxDAI,
        buy_token=COW,
        receiver=cowswap_test_account.address,
        sell_amount_before_fee=str(int(0.1e18)),
        kind=OrderKind.SELL,
        appData="0x0000000000000000000000000000000000000000000000000000000000000000",
        validFor=1080,
    )


def test_version(test_mock_client: CowClient) -> None:
    version = test_mock_client.get_version()
    assert version


class IdHolder:
    def __init__(self):
        self.ids = []


@pytest.fixture(scope="module")
def id_holder_fixture(test_mock_client: CowClient) -> Generator[IdHolder, None, None]:
    id_holder = IdHolder()
    yield id_holder
    # clean up
    test_mock_client.cancel_order_if_not_already_cancelled(id_holder.ids)


def test_get_order_status(test_mock_client: CowClient) -> None:
    order_uid = "0x2959dfad69782fa300d8e2897b7b5a340690515e45fcc529138ebe249faa2d48a7e93f5a0e718bddc654e525ea668c64fd57288266b2a01f"
    order_status = test_mock_client.get_order_status(order_uid)
    assert order_status == OrderStatus.CANCELLED


def test_post_order(
    test_mock_client: CowClient, test_quote: QuoteOutput, id_holder_fixture: IdHolder
) -> None:
    with patch(
        "prediction_market_agent_tooling.tools.cowswap.cow_client.CowClient.build_order_with_fee_and_sell_amounts",
        Mock(side_effect=fake_build_quote),
    ):
        # ToDo - do clean-up with created orders
        quote = test_mock_client.post_quote(test_quote)
        posted_order_id = test_mock_client.post_order(quote)
        assert posted_order_id is not None
        id_holder_fixture.ids.append(posted_order_id)
        # ToDo - clean-up
        status = test_mock_client.get_order_status(posted_order_id)
        assert status != OrderStatus.CANCELLED


def fake_build_quote(quote: QuoteOutput) -> dict:
    # We manipulate sellAmount to have a price ridiculously small, hence that will never get filled.
    new_sell_amount = int(quote.sell_amount) + int(quote.fee_amount)
    quote.sell_amount = str(new_sell_amount // 2)
    quote.fee_amount = "0"
    quote_dict = quote.dict(by_alias=True, exclude_none=True)
    return quote_dict


def test_post_quote(test_mock_client: CowClient, test_quote: QuoteOutput) -> None:
    result = test_mock_client.post_quote(test_quote)
    assert result is not None
    assert int(test_quote.sell_amount_before_fee) == (
        int(result.sell_amount) + int(result.fee_amount)
    )
