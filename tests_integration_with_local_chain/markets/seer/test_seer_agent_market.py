import pytest
from web3 import Web3

from prediction_market_agent_tooling.config import APIKeys
from prediction_market_agent_tooling.gtypes import USD
from prediction_market_agent_tooling.markets.agent_market import FilterBy, SortBy
from prediction_market_agent_tooling.markets.seer.seer import SeerAgentMarket
from prediction_market_agent_tooling.markets.seer.seer_subgraph_handler import (
    SeerSubgraphHandler,
)


def test_seer_place_bet(local_web3: Web3, test_keys: APIKeys) -> None:
    # We fetch the market with the highest liquidity because we expect quotes to be available for all outcome tokens.
    markets = SeerSubgraphHandler().get_binary_markets(
        filter_by=FilterBy.OPEN, limit=1, sort_by=SortBy.HIGHEST_LIQUIDITY
    )
    market_data_model = markets[0]
    agent_market = SeerAgentMarket.from_data_model(market_data_model)
    amount = USD(1.0)
    with pytest.raises(Exception) as e:
        # We expect an exception from Cow since test accounts don't have enough funds.
        agent_market.place_bet(
            api_keys=test_keys,
            outcome=True,
            amount=amount,
            auto_deposit=True,
            web3=local_web3,
        )
    assert "InsufficientBalance" in str(
        e
    ) or f"Balance 0 not enough for bet size {amount}" in str(e)
