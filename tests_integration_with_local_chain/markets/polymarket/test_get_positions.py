from web3 import Web3

from prediction_market_agent_tooling.markets.polymarket.api import get_user_positions


def test_get_positions() -> None:
    better_address = Web3.to_checksum_address(
        "0x461f3e886dca22e561eee224d283e08b8fb47a07"
    )  # one of polymarket most active traders
    pos = get_user_positions(user_id=better_address, condition_ids=None, limit=50)
    assert len(pos) > 0
