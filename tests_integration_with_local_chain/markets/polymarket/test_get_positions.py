import requests
from web3 import Web3

from prediction_market_agent_tooling.gtypes import ChecksumAddress
from prediction_market_agent_tooling.markets.polymarket.api import (
    PolymarketOrderByEnum,
    get_polymarkets_with_pagination,
    get_user_positions,
)
from prediction_market_agent_tooling.tools.utils import check_not_none


def get_random_token_holder() -> ChecksumAddress:
    recent_markets = get_polymarkets_with_pagination(
        limit=1, active=True, closed=False, order_by=PolymarketOrderByEnum.VOLUME_24HR
    )
    market = recent_markets[0]
    # 0x prefix is mandatory
    market_item = check_not_none(market.markets)[0]
    params = {"market": market_item.conditionId.to_0x_hex()}
    r = requests.get(url="https://data-api.polymarket.com/holders", params=params)
    data = r.json()
    return Web3.to_checksum_address(data[0]["holders"][0]["proxyWallet"])


def test_get_positions() -> None:
    # we get a positive, random token holder
    better_address = get_random_token_holder()
    pos = get_user_positions(user_id=better_address, condition_ids=None)
    assert len(pos) > 0
