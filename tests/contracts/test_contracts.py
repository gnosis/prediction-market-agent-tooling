from web3 import Web3

from prediction_market_agent_tooling.markets.omen.omen_contracts import sDaiContract


def test_sdai_asset_balance_of() -> None:
    assert (
        sDaiContract().get_asset_token_balance(
            Web3.to_checksum_address("0x7d3A0DA18e14CCb63375cdC250E8A8399997816F")
        )
        >= 0
    )
