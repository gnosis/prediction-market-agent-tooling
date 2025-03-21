import pytest
from web3 import Web3

from prediction_market_agent_tooling.config import APIKeys
from prediction_market_agent_tooling.gtypes import ChecksumAddress, Token
from prediction_market_agent_tooling.markets.omen.omen_contracts import (
    GNOContract,
    WrappedxDaiContract,
    sDaiContract,
)
from prediction_market_agent_tooling.tools.cow.cow_order import (
    get_buy_token_amount,
    swap_tokens_waiting,
)


def test_get_buy_token_amount() -> None:
    sell_amount = Token(0.1).as_wei
    buy_amount = get_buy_token_amount(
        amount_wei=sell_amount,
        sell_token=WrappedxDaiContract().address,
        buy_token=sDaiContract().address,
    )
    assert (
        buy_amount < sell_amount
    ), f"sDai should be more expensive than wxDai, but {buy_amount} >= {sell_amount}"


@pytest.mark.parametrize(
    "sell_token, buy_token",
    [
        (WrappedxDaiContract().address, sDaiContract().address),
        (sDaiContract().address, WrappedxDaiContract().address),
        (GNOContract().address, WrappedxDaiContract().address),
    ],
)
def test_swap_tokens_waiting(
    sell_token: ChecksumAddress,
    buy_token: ChecksumAddress,
    local_web3: Web3,
    test_keys: APIKeys,
) -> None:
    with pytest.raises(Exception) as e:
        swap_tokens_waiting(
            amount_wei=Token(0.1).as_wei,
            sell_token=sell_token,
            buy_token=buy_token,
            api_keys=test_keys,
            env="staging",
            web3=local_web3,
        )
    # This is raised in `post_order` which is last call when swapping tokens, anvil's accounts don't have any balance on real chain, so this is expected,
    # but still, it tests that all the logic behind calling CoW APIs is working correctly.
    assert "InsufficientBalance" in str(e)
