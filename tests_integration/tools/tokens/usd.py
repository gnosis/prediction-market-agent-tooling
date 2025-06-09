import time
from functools import cache

import numpy as np
import pytest
import requests
import tenacity

from prediction_market_agent_tooling.loggers import logger
from prediction_market_agent_tooling.markets.omen.omen_contracts import (
    ContractERC20OnGnosisChain,
    GNOContract,
    WETHContract,
    WrappedxDaiContract,
    sDaiContract,
)
from prediction_market_agent_tooling.tools.tokens.usd import (
    USD,
    CollateralToken,
    get_token_in_usd,
    get_usd_in_token,
)


@tenacity.retry(
    stop=tenacity.stop_after_attempt(3),
    wait=tenacity.wait_fixed(3),
    after=lambda x: logger.debug(
        f"_get_usd_price_coingecko failed, {x.attempt_number=}."
    ),
)
@cache  # Just a simple cache for the test, it's okay to have fixed data during the whole test.
def _get_usd_price_coingecko(token_id: str) -> USD:
    """
    Standardized way to get prices for us is CoW, as that is the Gnosis way to do it and agents can use it to swap tokens.
    However, in tests, try to get price from Coingecko as a 3rd source to compare our results.
    This endpoint works without API key.
    """
    response = requests.get(
        f"https://api.coingecko.com/api/v3/simple/price?ids={token_id}&vs_currencies=usd"
    )
    response.raise_for_status()
    time.sleep(1)  # Coingecko has rate limits, so don't spam it.
    return USD(response.json()[token_id]["usd"])


@pytest.mark.parametrize(
    "collateral_token_contract",
    [
        WrappedxDaiContract(),
        sDaiContract(),
        WETHContract(),
        GNOContract(),
    ],
)
def test_from_to_usd_is_equalish(
    collateral_token_contract: ContractERC20OnGnosisChain,
) -> None:
    five = USD(5)
    in_token = get_usd_in_token(five, collateral_token_contract.address)
    back_in_usd = get_token_in_usd(in_token, collateral_token_contract.address)
    assert np.isclose(five.value, back_in_usd.value, rtol=0.01)


@pytest.mark.parametrize(
    "collateral_token_contract, coingecko_id",
    [
        (WETHContract(), "ethereum"),
        (GNOContract(), "gnosis"),
    ],
)
def test_get_usd_in_token_is_equalish_to_coingecko(
    collateral_token_contract: ContractERC20OnGnosisChain, coingecko_id: str
) -> None:
    five = USD(5)
    in_token = get_usd_in_token(five, collateral_token_contract.address)
    coingecko_price = _get_usd_price_coingecko(coingecko_id)
    assert np.isclose(in_token.value, five / coingecko_price, rtol=0.01)


@pytest.mark.parametrize(
    "collateral_token_contract, coingecko_id",
    [
        (WETHContract(), "ethereum"),
        (GNOContract(), "gnosis"),
    ],
)
def test_get_token_in_usd_is_equalish_to_coingecko(
    collateral_token_contract: ContractERC20OnGnosisChain, coingecko_id: str
) -> None:
    token = CollateralToken(5)
    in_usd = get_token_in_usd(token, collateral_token_contract.address)
    coingecko_price = _get_usd_price_coingecko(coingecko_id) * token.value
    assert np.isclose(in_usd.value, coingecko_price.value, rtol=0.01)
