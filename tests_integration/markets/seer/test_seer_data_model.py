import numpy as np
from web3 import Web3

from prediction_market_agent_tooling.markets.agent_market import SortBy, FilterBy
from prediction_market_agent_tooling.markets.seer.data_models import SeerOutcomeEnum
from prediction_market_agent_tooling.markets.seer.seer_subgraph_handler import (
    SeerSubgraphHandler,
)
from prediction_market_agent_tooling.tools.cow.cow_manager import CowManager


def test_current_p_yes(
    seer_subgraph_handler_test: SeerSubgraphHandler, cow_manager: CowManager
) -> None:
    # We fetch many markets because non YES/NO markets are also fetched.
    market = seer_subgraph_handler_test.get_binary_markets(
        limit=100, sort_by=SortBy.HIGHEST_LIQUIDITY, filter_by=FilterBy.OPEN
    )[0]
    yes_idx = market.outcome_as_enums[SeerOutcomeEnum.POSITIVE]
    yes_token = market.wrapped_tokens[yes_idx]
    yes_price = market._get_price_for_token(Web3.to_checksum_address(yes_token))

    no_idx = market.outcome_as_enums[SeerOutcomeEnum.NEGATIVE]
    no_token = market.wrapped_tokens[no_idx]
    no_price = market._get_price_for_token(Web3.to_checksum_address(no_token))

    invalid_idx = market.outcome_as_enums[SeerOutcomeEnum.NEUTRAL]
    invalid_token = market.wrapped_tokens[invalid_idx]
    invalid_price = market._get_price_for_token(Web3.to_checksum_address(invalid_token))

    current_p_yes = market.current_p_yes
    expected_p_yes = yes_price / (yes_price + no_price + invalid_price)
    assert np.isclose(current_p_yes, expected_p_yes, atol=0.01)
