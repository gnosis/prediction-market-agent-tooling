import numpy as np
import pytest
from web3 import Web3

from prediction_market_agent_tooling.config import APIKeys
from prediction_market_agent_tooling.gtypes import ChecksumAddress, CollateralToken
from prediction_market_agent_tooling.markets.omen.omen_contracts import (
    GNOContract,
    WrappedxDaiContract,
    sDaiContract,
)
from prediction_market_agent_tooling.tools.cow.cow_order import (
    get_buy_token_amount,
    get_sell_token_amount,
    swap_tokens_waiting,
)


def test_get_buy_token_amount() -> None:
    sell_amount = CollateralToken(0.1).as_wei
    buy_amount = get_buy_token_amount(
        sell_amount=sell_amount,
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
def test_get_buy_vs_sell_token_amount(
    sell_token: ChecksumAddress,
    buy_token: ChecksumAddress,
) -> None:
    wanted_in_buying_token = CollateralToken(10)
    calculated_how_much_do_i_need_to_sell = get_sell_token_amount(
        buy_amount=wanted_in_buying_token.as_wei,
        sell_token=sell_token,
        buy_token=buy_token,
    )
    how_much_would_i_get_from_calculated = get_buy_token_amount(
        sell_amount=calculated_how_much_do_i_need_to_sell,
        sell_token=sell_token,
        buy_token=buy_token,
    )
    assert np.isclose(
        wanted_in_buying_token.value,
        how_much_would_i_get_from_calculated.as_token.value,
        rtol=0.01,
    )


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
            amount_wei=CollateralToken(1).as_wei,
            sell_token=sell_token,
            buy_token=buy_token,
            api_keys=test_keys,
            web3=local_web3,
        )
    # This is raised in `post_order` which is last call when swapping tokens, anvil's accounts don't have any balance on real chain, so this is expected,
    # but still, it tests that all the logic behind calling CoW APIs is working correctly.
    assert "InsufficientBalance" in str(e)
