import pytest
from web3 import Web3

from prediction_market_agent_tooling.config import APIKeys
from prediction_market_agent_tooling.gtypes import xdai_type
from prediction_market_agent_tooling.markets.omen.omen_contracts import (
    WrappedxDaiContract,
    sDaiContract,
)
from prediction_market_agent_tooling.tools.cow.cow_order import swap_tokens_waiting


def test_swap_tokens_waiting(local_web3: Web3, test_keys: APIKeys) -> None:
    with pytest.raises(Exception) as e:
        swap_tokens_waiting(
            amount=xdai_type(0.1),
            sell_token=WrappedxDaiContract().address,
            buy_token=sDaiContract().address,
            api_keys=test_keys,
            env="staging",
            web3=local_web3,
        )
    # This is raised in `post_order` which is last call when swapping tokens, anvil's accounts don't have any balance on real chain, so this is expected,
    # but still, it tests that all the logic behind calling CoW APIs is working correctly.
    assert "InsufficientBalance" in str(e)
