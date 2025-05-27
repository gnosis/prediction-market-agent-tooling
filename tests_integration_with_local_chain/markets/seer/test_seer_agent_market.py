from unittest.mock import patch

import pytest
from web3 import Web3

from prediction_market_agent_tooling.config import APIKeys
from prediction_market_agent_tooling.gtypes import USD, OutcomeStr
from prediction_market_agent_tooling.markets.agent_market import FilterBy, SortBy
from prediction_market_agent_tooling.markets.seer.seer import SeerAgentMarket
from prediction_market_agent_tooling.markets.seer.seer_subgraph_handler import (
    SeerSubgraphHandler,
)
from prediction_market_agent_tooling.tools.utils import check_not_none


def test_seer_place_bet(
    local_web3: Web3,
    test_keys: APIKeys,
    seer_subgraph_handler_test: SeerSubgraphHandler,
) -> None:
    # We fetch the market with the highest liquidity because we expect quotes to be available for all outcome tokens.
    markets = SeerSubgraphHandler().get_markets(
        filter_by=FilterBy.OPEN,
        limit=1,
        sort_by=SortBy.HIGHEST_LIQUIDITY,
        include_categorical_markets=True,
    )
    market_data_model = markets[0]
    agent_market = SeerAgentMarket.from_data_model_with_subgraph(
        market_data_model,
        seer_subgraph=seer_subgraph_handler_test,
        must_have_prices=True,
    )
    agent_market = check_not_none(agent_market)
    amount = USD(1.0)
    with pytest.raises(Exception) as e:
        # We expect an exception from Cow since test accounts don't have enough funds.
        agent_market.place_bet(
            api_keys=test_keys,
            outcome=OutcomeStr("Yes"),
            amount=amount,
            auto_deposit=True,
            web3=local_web3,
        )
    assert "InsufficientBalance" in str(
        e
    ) or f"Balance 0 not enough for bet size {amount}" in str(e)


def test_seer_place_bet_via_pools(
    local_web3: Web3,
    test_keys: APIKeys,
    seer_subgraph_handler_test: SeerSubgraphHandler,
) -> None:
    # ToDo
    # . 1. Mock cow, throw Timeout

    # We fetch the market with the highest liquidity because we expect quotes to be available for all outcome tokens.
    markets = SeerSubgraphHandler().get_markets(
        filter_by=FilterBy.OPEN,
        limit=1,
        sort_by=SortBy.HIGHEST_LIQUIDITY,
        include_categorical_markets=True,
    )
    market_data_model = markets[0]
    agent_market = SeerAgentMarket.from_data_model_with_subgraph(
        market_data_model,
        seer_subgraph=seer_subgraph_handler_test,
        must_have_prices=True,
    )
    agent_market = check_not_none(agent_market)
    outcome = agent_market.outcomes[0]
    # Mock swap_tokens_waiting to throw a TimeoutError immediately
    with patch(
        "prediction_market_agent_tooling.markets.seer.seer.swap_tokens_waiting"
    ) as mock_swap:
        mock_swap.side_effect = TimeoutError("Mocked timeout error")

        agent_market.place_bet(
            outcome=outcome,
            amount=USD(1.0),
            auto_deposit=True,
            web3=local_web3,
            api_keys=test_keys,
        )
    # . 4. assert outcome token balance increases
    final_outcome_token_balance = agent_market.get_token_balance(
        user_id=test_keys.bet_from_address, outcome=outcome, web3=local_web3
    )
    assert final_outcome_token_balance > 0
