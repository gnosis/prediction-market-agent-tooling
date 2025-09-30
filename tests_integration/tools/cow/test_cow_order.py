import pytest
from web3 import Web3

from prediction_market_agent_tooling.gtypes import HexBytes
from prediction_market_agent_tooling.tools.cow.cow_order import (
    get_order_by_uid,
    get_orders_by_owner,
)


def test_orders_by_owner() -> None:
    example_address_with_orders = Web3.to_checksum_address(
        "0xd0363Ccd573163DF94b754Ca00c0acA2bb66b748"
    )  # coinflip Seer
    prev_orders = get_orders_by_owner(owner=example_address_with_orders)
    assert len(prev_orders) > 0


@pytest.mark.asyncio
async def test_order_by_uid() -> None:
    uid = HexBytes(
        "0xdedd2447008592d047b1cab4f0990ae1340ef234019abaea6cbb2fabc74d9b1f3564e1e403c050248027f870eee032384b48f2d165822589"
    )
    order = await get_order_by_uid(uid=uid)
    assert (
        order.appData
        == "0x64e80e8f762315c3af2b7efc36c39b41ead8ab8593d816a070359428dae97f03"  # web3-private-key-ok
    )
