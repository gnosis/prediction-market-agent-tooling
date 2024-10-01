import json
import time
from datetime import timedelta

import pytest

from prediction_market_agent_tooling.config import APIKeys
from prediction_market_agent_tooling.gtypes import omen_outcome_type, xdai_type
from prediction_market_agent_tooling.markets.omen.data_models import (
    OMEN_BINARY_MARKET_OUTCOMES,
    TEST_CATEGORY,
)
from prediction_market_agent_tooling.markets.omen.omen import (
    OmenMarket,
    omen_create_market_tx,
)
from prediction_market_agent_tooling.markets.omen.omen_contracts import (
    OMEN_DEFAULT_MARKET_FEE_PERC,
    WrappedxDaiContract,
)
from prediction_market_agent_tooling.markets.omen.omen_subgraph_handler import (
    OmenSubgraphHandler,
)
from prediction_market_agent_tooling.tools.utils import utcnow
from prediction_market_agent_tooling.tools.web3_utils import xdai_to_wei
from tests.utils import RUN_PAID_TESTS


@pytest.mark.skipif(not RUN_PAID_TESTS, reason="This test costs money to run.")
def test_created_market_corresponds_to_subgraph_market() -> None:
    api_keys = APIKeys()

    # Create the market.
    close_in = 60
    question = f"Will GNO hit $1000 {close_in} seconds from now?"
    created_time = utcnow()
    closing_time = created_time + timedelta(seconds=close_in)
    funds = xdai_type(0.1)
    finalization_wait_time_seconds = 60
    category = TEST_CATEGORY
    language = "en"
    distribution_hint = [
        omen_outcome_type(xdai_to_wei(xdai_type(0.05))),  # 75% for yes
        omen_outcome_type(xdai_to_wei(xdai_type(0.15))),  # 25% for now
    ]
    assert sum(distribution_hint) == 2 * xdai_to_wei(
        funds
    ), "This should be equal, we are testing skewed markets."

    created_market = omen_create_market_tx(
        api_keys=api_keys,
        initial_funds=funds,
        fee_perc=OMEN_DEFAULT_MARKET_FEE_PERC,
        question=question,
        closing_time=closing_time,
        category=category,
        language=language,
        outcomes=OMEN_BINARY_MARKET_OUTCOMES,
        finalization_timeout=timedelta(seconds=finalization_wait_time_seconds),
        collateral_token_address=WrappedxDaiContract().address,
        auto_deposit=True,
        distribution_hint=distribution_hint,
    )

    # Convert to omen market
    from_created_market = OmenMarket.from_created_market(created_market)
    print(f"Market created at {from_created_market.url}")

    # Wait for the subgraph to update itself.
    time.sleep(30)

    # Load from subgraph.
    from_subgraph_market = OmenSubgraphHandler().get_omen_market_by_market_id(
        from_created_market.id
    )

    # Save because otherwise it's hard to debug
    with open("tests_files/created_market.json", "w") as f:
        json.dump(created_market.model_dump(), f, indent=2)
    with open("tests_files/from_created_market.json", "w") as f:
        json.dump(from_created_market.model_dump(), f, indent=2)
    with open("tests_files/from_subgraph_market.json", "w") as f:
        json.dump(from_subgraph_market.model_dump(), f, indent=2)

    # Compare!
    assert from_created_market == from_subgraph_market
