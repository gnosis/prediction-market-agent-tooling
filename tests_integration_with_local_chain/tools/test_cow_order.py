import os

import numpy as np
import pytest
from cowdao_cowpy.common.chains import Chain
from cowdao_cowpy.order_book.config import Envs
from cowdao_cowpy.order_book.generated.model import OrderStatus
from pydantic import SecretStr
from web3 import Web3

from prediction_market_agent_tooling.config import APIKeys
from prediction_market_agent_tooling.gtypes import (
    ChecksumAddress,
    CollateralToken,
    PrivateKey,
)
from prediction_market_agent_tooling.markets.omen.omen_contracts import (
    GNOContract,
    WrappedxDaiContract,
    sDaiContract,
)
from prediction_market_agent_tooling.tools.cow.cow_order import (
    build_account,
    cancel_order,
    do_swap,
    get_buy_token_amount_else_raise,
    get_order_book_api,
    get_sell_token_amount,
    handle_allowance,
    swap_tokens_waiting,
)
from prediction_market_agent_tooling.tools.utils import check_not_none
from tests.utils import RUN_PAID_TESTS


@pytest.mark.skip("Cow integration still in progress")
def test_get_buy_token_amount() -> None:
    sell_amount = CollateralToken(0.1).as_wei
    buy_amount = get_buy_token_amount_else_raise(
        sell_amount=sell_amount,
        sell_token=WrappedxDaiContract().address,
        buy_token=sDaiContract().address,
    )
    assert (
        buy_amount < sell_amount
    ), f"sDai should be more expensive than wxDai, but {buy_amount} >= {sell_amount}"


@pytest.mark.skip("Cow integration still in progress")
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
    how_much_would_i_get_from_calculated = get_buy_token_amount_else_raise(
        sell_amount=calculated_how_much_do_i_need_to_sell,
        sell_token=sell_token,
        buy_token=buy_token,
    )
    assert np.isclose(
        wanted_in_buying_token.value,
        how_much_would_i_get_from_calculated.as_token.value,
        rtol=0.01,
    )


@pytest.mark.skip("Cow integration still in progress")
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


@pytest.mark.asyncio
@pytest.mark.skipif(
    not RUN_PAID_TESTS, reason="We don't want to spam Cow APIs on every test run."
)
async def test_cow_cancellation(local_web3: Web3) -> None:
    test_keys = APIKeys(
        BET_FROM_PRIVATE_KEY=PrivateKey(
            SecretStr(check_not_none(os.getenv("COWSWAP_TEST_PRIVATE_KEY")))
        )
    )

    # must have a positive balance on Gnosis chain
    sell_token = WrappedxDaiContract().address
    buy_token = sDaiContract().address
    env: Envs = "prod"
    chain: Chain = Chain.GNOSIS

    # 1. Create order (unrealistic so that it's not filled)
    amount_wei = CollateralToken(0.01).as_wei
    handle_allowance(
        api_keys=test_keys,
        sell_token=sell_token,
        amount_wei=amount_wei,
        web3=local_web3,
    )
    order_book_api = get_order_book_api(env=env, chain=chain)

    # We expect the order to not be filled during the test (small amount)

    build_account(test_keys.bet_from_private_key)
    order = await do_swap(
        api_keys=test_keys,
        amount_wei=amount_wei,
        sell_token=sell_token,
        buy_token=buy_token,
        env=env,
        chain=chain,
    )

    await cancel_order(
        order_uids=[order.uid.root], api_keys=test_keys, env=env, chain=chain
    )

    updated_order = await order_book_api.get_order_by_uid(order.uid)
    assert updated_order.status == OrderStatus.cancelled
