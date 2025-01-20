import numpy as np
import pytest

from prediction_market_agent_tooling.config import APIKeys
from prediction_market_agent_tooling.gtypes import wei_type, xdai_type
from prediction_market_agent_tooling.markets.omen.omen_contracts import GNOContract
from prediction_market_agent_tooling.tools.cow.cow_order import get_buy_token_amount
from prediction_market_agent_tooling.tools.tokens.auto_deposit import (
    auto_deposit_collateral_token,
)
from prediction_market_agent_tooling.tools.tokens.auto_withdraw import (
    auto_withdraw_collateral_token,
)
from prediction_market_agent_tooling.tools.tokens.main_token import KEEPING_ERC20_TOKEN
from prediction_market_agent_tooling.tools.web3_utils import xdai_to_wei
from tests.utils import RUN_PAID_TESTS


@pytest.mark.skipif(not RUN_PAID_TESTS, reason="This test costs money to run.")
def test_auto_deposit_and_withdraw() -> None:
    """
    auto_deposit and auto_withdraw that works with xDai -> wxDai -> sDai (and back) is tested in integration tests with local chain.
    For other tokens, we need CoW, but that isn't usable in the local chain (calls 3rd party API),
    so this test is marked to be skipped and needs to be run manually.
    """
    rtol = 0.05  # Allow % change in amounts, prices constantly changes, so after we sell the token, we can't expect the same amount back.
    api_keys = APIKeys()

    token_1 = (
        KEEPING_ERC20_TOKEN  # Token to start and end with (first sell, then buy back).
    )
    token_2 = GNOContract()  # Simulated "collateral token".

    # How much we want to sell of token_1.
    amount_in_token_1_to_sell = xdai_to_wei(xdai_type(1))
    amount_in_token_2_to_get = get_buy_token_amount(
        amount_in_token_1_to_sell, token_1.address, token_2.address
    )
    # auto_deposit will deposit only as much as is needed, so add the existing balance to the amount we want to deposit in this test.
    initial_balance_of_token_2_in_token_1_units = get_buy_token_amount(
        token_2.balanceOf(api_keys.bet_from_address), token_2.address, token_1.address
    )
    amount_in_token_1 = wei_type(
        amount_in_token_1_to_sell + initial_balance_of_token_2_in_token_1_units
    )
    # And how much we expect to have in token_2 after the sell.
    amount_in_token_2 = get_buy_token_amount(
        amount_in_token_1, token_1.address, token_2.address
    )

    before_deposit_balance_token_1 = token_1.balanceOf(api_keys.bet_from_address)
    before_deposit_balance_token_2 = token_2.balanceOf(api_keys.bet_from_address)

    auto_deposit_collateral_token(
        collateral_token_contract=token_2,
        amount_wei=amount_in_token_1,
        api_keys=api_keys,
    )

    after_deposit_balance_token_1 = token_1.balanceOf(api_keys.bet_from_address)
    after_deposit_balance_token_2 = token_2.balanceOf(api_keys.bet_from_address)

    assert (
        after_deposit_balance_token_1 < before_deposit_balance_token_1
    ), f"{after_deposit_balance_token_1} !< {before_deposit_balance_token_1}"
    assert (
        after_deposit_balance_token_2 > before_deposit_balance_token_2
    ), f"{after_deposit_balance_token_2} !> {before_deposit_balance_token_2}"
    assert np.isclose(
        after_deposit_balance_token_1,
        before_deposit_balance_token_1 - amount_in_token_1_to_sell,
        rtol=rtol,
    ), f"{after_deposit_balance_token_1} !~= {before_deposit_balance_token_1 - amount_in_token_1_to_sell}"
    assert np.isclose(
        after_deposit_balance_token_2,
        before_deposit_balance_token_2 + amount_in_token_2_to_get,
        rtol=rtol,
    ), f"{after_deposit_balance_token_2} !~= {before_deposit_balance_token_2 + amount_in_token_2_to_get}"
    assert np.isclose(
        amount_in_token_2, after_deposit_balance_token_2, rtol=rtol
    ), f"{amount_in_token_2} !~= {after_deposit_balance_token_2}"

    auto_withdraw_collateral_token(
        token_2,
        amount_wei=amount_in_token_2_to_get,
        api_keys=api_keys,
    )

    after_withdraw_balance_token_1 = token_1.balanceOf(api_keys.bet_from_address)
    after_withdraw_balance_token_2 = token_2.balanceOf(api_keys.bet_from_address)

    assert (
        after_withdraw_balance_token_1 > after_deposit_balance_token_1
    ), f"{after_withdraw_balance_token_1} !> {after_deposit_balance_token_1}"
    assert (
        after_withdraw_balance_token_2 < after_deposit_balance_token_2
    ), f"{after_withdraw_balance_token_2} !< {after_deposit_balance_token_2}"
    assert np.isclose(
        after_withdraw_balance_token_1,
        after_deposit_balance_token_1 + amount_in_token_1_to_sell,
        rtol=rtol,
    ), f"{after_withdraw_balance_token_1} !~= {after_deposit_balance_token_1 + amount_in_token_1_to_sell}"
    assert np.isclose(
        after_withdraw_balance_token_2,
        after_deposit_balance_token_2 - amount_in_token_2_to_get,
        rtol=rtol,
    ), f"{after_withdraw_balance_token_2} !~= {after_deposit_balance_token_2 - amount_in_token_2_to_get}"
