from web3 import Web3

from prediction_market_agent_tooling.tools.cow.cow_order import (
    get_orders_by_owner,
)


def test_orders_by_owner() -> None:
    example_address_with_orders = Web3.to_checksum_address(
        "0xd0363Ccd573163DF94b754Ca00c0acA2bb66b748"
    )  # coinflip Seer
    prev_orders = get_orders_by_owner(owner=example_address_with_orders)
    assert len(prev_orders) > 0
