import pytest
from web3 import Web3

from prediction_market_agent_tooling.gtypes import Token
from prediction_market_agent_tooling.markets.omen.omen_contracts import sDaiContract
from prediction_market_agent_tooling.tools.cow.cow_manager import (
    CowManager,
    NoLiquidityAvailableOnCowException,
)


@pytest.fixture(scope="module")
def test_manager() -> CowManager:
    return CowManager()


def test_nonexistent_quote(test_manager: CowManager) -> None:
    collateral_token = sDaiContract().address
    token_without_liquidity = Web3.to_checksum_address(
        "0x7cefb84cf95640132adb31ed635e31d40d7e3322"
    )

    with pytest.raises(NoLiquidityAvailableOnCowException):
        test_manager.get_quote(
            collateral_token=collateral_token,
            buy_token=token_without_liquidity,
            sell_amount=Token(1).as_wei,
        )
