import numpy as np
import pytest

from prediction_market_agent_tooling.config import APIKeys
from prediction_market_agent_tooling.gtypes import USD
from prediction_market_agent_tooling.markets.omen.omen_contracts import (
    ContractERC20OnGnosisChain,
    GNOContract,
    WETHContract,
    sDaiContract,
)
from prediction_market_agent_tooling.tools.tokens.auto_deposit import (
    auto_deposit_collateral_token,
)
from prediction_market_agent_tooling.tools.tokens.auto_withdraw import (
    auto_withdraw_collateral_token,
)
from prediction_market_agent_tooling.tools.tokens.main_token import KEEPING_ERC20_TOKEN
from prediction_market_agent_tooling.tools.tokens.usd import (
    get_token_in_usd,
    get_usd_in_token,
)
from tests.utils import RUN_PAID_TESTS


@pytest.mark.skipif(not RUN_PAID_TESTS, reason="This test costs money to run.")
@pytest.mark.parametrize(
    "collateral_token_contract",
    [
        sDaiContract(),
        WETHContract(),
        GNOContract(),
    ],
)
def test_auto_deposit_and_withdraw(
    collateral_token_contract: ContractERC20OnGnosisChain,
) -> None:
    """
    We need CoW, but that isn't usable in the local chain (calls 3rd party API),
    so this test is marked to be skipped and needs to be run manually.
    """
    rtol = 0.05  # Allow % change in amounts, prices constantly changes, so after we sell the token, we can't expect the same amount back.
    api_keys = APIKeys()

    # how much we want to deposit
    to_deposit = USD(1)

    # how much is that in main token
    to_deposit_as_keeping_token = get_usd_in_token(
        to_deposit,
        KEEPING_ERC20_TOKEN.address,
    )
    # and in the other token
    to_deposit_as_col_token = get_usd_in_token(
        to_deposit,
        collateral_token_contract.address,
    )

    # auto_deposit will deposit only as much as is needed, so add the existing balance to the amount we want to deposit in this test.
    initial_balance_of_col_token_in_usd = get_token_in_usd(
        collateral_token_contract.balance_of_in_tokens(api_keys.bet_from_address),
        collateral_token_contract.address,
    )
    total_amount_in_usd = initial_balance_of_col_token_in_usd + to_deposit
    # And how much we expect to have in col_token after the deposit.
    total_amount_in_col_token = get_usd_in_token(
        total_amount_in_usd,
        collateral_token_contract.address,
    )

    before_deposit_balance_main_token = KEEPING_ERC20_TOKEN.balance_of_in_tokens(
        api_keys.bet_from_address
    )
    before_deposit_balance_col_token = collateral_token_contract.balance_of_in_tokens(
        api_keys.bet_from_address
    )

    auto_deposit_collateral_token(
        collateral_token_contract,
        total_amount_in_usd,
        api_keys=api_keys,
    )

    after_deposit_balance_main_token = KEEPING_ERC20_TOKEN.balance_of_in_tokens(
        api_keys.bet_from_address
    )
    after_deposit_balance_col_token = collateral_token_contract.balance_of_in_tokens(
        api_keys.bet_from_address
    )

    assert (
        after_deposit_balance_main_token <= before_deposit_balance_main_token
    ), "Should be less or equal, because if it was 0, then it should have been deposited and then used which would result in 0. Or, if it was more, it should have be withdrawn from it."
    assert (
        after_deposit_balance_col_token > before_deposit_balance_col_token
    ), "Should be more, because we swapped into it."
    assert after_deposit_balance_main_token == 0 or np.isclose(
        after_deposit_balance_main_token.value,
        (before_deposit_balance_main_token - to_deposit_as_keeping_token).value,
        rtol=rtol,
    ), "Should be 0 if it was deposited and then used, or should be less by the amount we sold."
    assert np.isclose(
        after_deposit_balance_col_token.value,
        (before_deposit_balance_col_token + to_deposit_as_col_token).value,
        rtol=rtol,
    ), "Should be more by the amount we bought."
    assert np.isclose(
        total_amount_in_col_token.value,
        after_deposit_balance_col_token.value,
        rtol=rtol,
    ), "Should be equal, because we bought exactly as much as we expected in the beginning."

    auto_withdraw_collateral_token(
        collateral_token_contract,
        amount_wei=to_deposit_as_col_token.as_wei,
        api_keys=api_keys,
    )

    after_withdraw_balance_main_token = KEEPING_ERC20_TOKEN.balance_of_in_tokens(
        api_keys.bet_from_address
    )
    after_withdraw_balance_col_token = collateral_token_contract.balance_of_in_tokens(
        api_keys.bet_from_address
    )

    assert (
        after_withdraw_balance_main_token > after_deposit_balance_main_token
    ), "When we withdraw it back, it should be always more then what we had after the deposit."
    assert (
        after_withdraw_balance_col_token < after_deposit_balance_col_token
    ), "Should be less, because we sold it for the main token."
    assert np.isclose(
        after_withdraw_balance_main_token.value,
        (after_deposit_balance_main_token + to_deposit_as_keeping_token).value,
        rtol=rtol,
    ), "Should be more by the amount we bought."
    assert np.isclose(
        after_withdraw_balance_col_token.value,
        (after_deposit_balance_col_token - to_deposit_as_col_token).value,
        rtol=rtol,
    ), "Should be less by the amount we sold."
