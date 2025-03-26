from cachetools import TTLCache, cached
from eth_typing.evm import ChecksumAddress

from prediction_market_agent_tooling.gtypes import (
    USD,
    ChecksumAddress,
    CollateralToken,
    xDai,
)
from prediction_market_agent_tooling.markets.omen.omen_constants import (
    SDAI_CONTRACT_ADDRESS,
    WRAPPED_XDAI_CONTRACT_ADDRESS,
)
from prediction_market_agent_tooling.tools.contract import ContractERC4626OnGnosisChain
from prediction_market_agent_tooling.tools.cow.cow_order import get_buy_token_amount


def get_usd_in_xdai(amount: USD) -> xDai:
    # xDai is stable coin against USD, so for simplicity we just cast it.
    return xDai(amount.value)


def get_xdai_in_usd(amount: xDai) -> USD:
    # xDai is stable coin against USD, so for simplicity we just cast it.
    return USD(amount.value)


def get_usd_in_token(amount: USD, token_address: ChecksumAddress) -> CollateralToken:
    rate = get_single_usd_to_token_rate(token_address)
    return CollateralToken(amount.value * rate.value)


def get_token_in_usd(amount: CollateralToken, token_address: ChecksumAddress) -> USD:
    rate = get_single_token_to_usd_rate(token_address)
    return USD(amount.value * rate.value)


# A short cache to not spam CoW and prevent timeouts, but still have relatively fresh data.
@cached(TTLCache(maxsize=100, ttl=5 * 60))
def get_single_token_to_usd_rate(token_address: ChecksumAddress) -> USD:
    # (w)xDai is a stable coin against USD, so use it to estimate USD worth.
    if WRAPPED_XDAI_CONTRACT_ADDRESS == token_address:
        return USD(1.0)
    # sDai is ERC4626 with wxDai as asset, we can take the rate directly from there instead of calling CoW.
    if SDAI_CONTRACT_ADDRESS == token_address:
        return USD(
            ContractERC4626OnGnosisChain(address=SDAI_CONTRACT_ADDRESS)
            .convertToAssets(CollateralToken(1).as_wei)
            .as_token.value
        )
    in_wei = get_buy_token_amount(
        sell_amount=CollateralToken(1).as_wei,
        sell_token=token_address,
        buy_token=WRAPPED_XDAI_CONTRACT_ADDRESS,
    )
    in_token = in_wei.as_token
    return USD(in_token.value)


# A short cache to not spam CoW and prevent timeouts, but still have relatively fresh data.
@cached(TTLCache(maxsize=100, ttl=5 * 60))
def get_single_usd_to_token_rate(token_address: ChecksumAddress) -> CollateralToken:
    # (w)xDai is a stable coin against USD, so use it to estimate USD worth.
    if WRAPPED_XDAI_CONTRACT_ADDRESS == token_address:
        return CollateralToken(1.0)
    # sDai is ERC4626 with wxDai as asset, we can take the rate directly from there instead of calling CoW.
    if SDAI_CONTRACT_ADDRESS == token_address:
        return CollateralToken(
            ContractERC4626OnGnosisChain(address=SDAI_CONTRACT_ADDRESS)
            .convertToShares(CollateralToken(1).as_wei)
            .as_token.value
        )
    in_wei = get_buy_token_amount(
        sell_amount=CollateralToken(1).as_wei,
        sell_token=WRAPPED_XDAI_CONTRACT_ADDRESS,
        buy_token=token_address,
    )
    in_token = in_wei.as_token
    return CollateralToken(in_token.value)
