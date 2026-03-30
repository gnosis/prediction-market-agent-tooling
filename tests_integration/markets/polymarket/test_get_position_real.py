import pytest
import requests
from web3 import Web3

from prediction_market_agent_tooling.gtypes import USD, ChecksumAddress, OutcomeToken
from prediction_market_agent_tooling.markets.polymarket.api import (
    PolymarketOrderByEnum,
    get_polymarkets_with_pagination,
)
from prediction_market_agent_tooling.markets.polymarket.polymarket import (
    PolymarketAgentMarket,
)
from prediction_market_agent_tooling.markets.polymarket.polymarket_subgraph_handler import (
    PolymarketSubgraphHandler,
)
from prediction_market_agent_tooling.tools.utils import check_not_none


def _get_market_and_holder() -> tuple[PolymarketAgentMarket, ChecksumAddress]:
    """Find an active market with a known position holder via the Polymarket Data API."""
    markets_data = get_polymarkets_with_pagination(
        limit=5,
        active=True,
        closed=False,
        order_by=PolymarketOrderByEnum.VOLUME_24HR,
    )
    assert markets_data, "No active markets found on Polymarket"

    for market_data in markets_data:
        market_item = check_not_none(market_data.markets)[0]
        condition_id = market_item.conditionId

        conditions = PolymarketSubgraphHandler().get_conditions(
            condition_ids=[condition_id]
        )
        condition_dict = {c.id: c for c in conditions}

        market = PolymarketAgentMarket.from_data_model(market_data, condition_dict)
        if market is None:
            continue

        params = {"market": condition_id.to_0x_hex()}
        r = requests.get(url="https://data-api.polymarket.com/holders", params=params)
        data = r.json()

        for entry in data:
            if entry.get("holders"):
                holder = Web3.to_checksum_address(entry["holders"][0]["proxyWallet"])
                return market, holder

    pytest.fail(
        "Could not find any market with position holders among top 5 active markets"
    )


def test_get_position_real() -> None:
    """Verify get_position() maps live Data API response into ExistingPosition correctly."""
    market, holder = _get_market_and_holder()
    position = market.get_position(user_id=holder)

    assert (
        position is not None
    ), f"Expected position for holder {holder} in market {market.id}, got None"
    assert position.market_id == market.id

    for outcome in market.outcomes:
        assert outcome in position.amounts_ot
        assert outcome in position.amounts_potential
        assert outcome in position.amounts_current
        assert position.amounts_ot[outcome] >= OutcomeToken(0)
        assert position.amounts_current[outcome] >= USD(0)
