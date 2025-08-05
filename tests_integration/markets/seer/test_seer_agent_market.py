from unittest.mock import Mock, patch

from web3 import Web3

from prediction_market_agent_tooling.config import APIKeys
from prediction_market_agent_tooling.gtypes import CollateralToken, HexBytes, HexStr
from prediction_market_agent_tooling.markets.agent_market import FilterBy, SortBy
from prediction_market_agent_tooling.markets.seer.seer import (
    SHARED_CACHE,
    SeerAgentMarket,
)
from prediction_market_agent_tooling.markets.seer.seer_subgraph_handler import (
    SeerSubgraphHandler,
)
from prediction_market_agent_tooling.tools.datetime_utc import DatetimeUTC
from prediction_market_agent_tooling.tools.utils import check_not_none


def test_seer_bet_on_market_since(
    seer_subgraph_handler_test: SeerSubgraphHandler,
) -> None:
    # We don't want to call Cow during every test.
    with patch(
        "prediction_market_agent_tooling.markets.seer.price_manager.PriceManager.get_price_for_token",
        return_value=CollateralToken(1),
    ):
        market_id = HexBytes(HexStr("0x76bc483691d926590ee4a540d619ef1c9716dfbb"))
        market = seer_subgraph_handler_test.get_market_by_id(market_id)

        keys = Mock(spec=APIKeys)
        keys.bet_from_address = Web3.to_checksum_address(
            "0xd0363Ccd573163DF94b754Ca00c0acA2bb66b748"
        )
        agent_market = check_not_none(
            SeerAgentMarket.from_data_model_with_subgraph(
                model=market,
                seer_subgraph=seer_subgraph_handler_test,
                must_have_prices=False,
            )
        )
        # cow order id 0xcd7f4456ce9756977aa1cca8b1f8eb19f0a9827a6ebfbe2407cda57913831640d0363ccd573163df94b754ca00c0aca2bb66b7486834b44f
        order_date = DatetimeUTC(2025, 5, 25)
        date_diff = DatetimeUTC.now() - order_date
        result = agent_market.have_bet_on_market_since(keys=keys, since=date_diff)
        assert result


def test_seer_has_liquidity_caching(
    seer_subgraph_handler_test: SeerSubgraphHandler,
) -> None:
    """
    Tests that the `has_liquidity` method correctly caches its result
    across different instances of a market, based on the market's ID.

    The strategy is to mock the *internal* method `has_liquidity_for_outcome`
    and count its calls. If the cache is working, this internal method
    should only be called on the first invocation for a given market ID.
    """
    # --- Setup ---
    # To ensure the test is reliable and independent, we clear the shared cache
    # before running any assertions.
    SHARED_CACHE.clear()

    # We mock the method that is called *inside* the cached method.
    # This allows us to spy on its execution. We replace it with a mock
    # that always returns True for simplicity.
    with patch(
        "prediction_market_agent_tooling.markets.seer.seer.SeerAgentMarket.has_liquidity_for_outcome",
        return_value=True,
    ) as mock_has_liquidity_for_outcome:
        # --- Test Case 1: Caching with two instances of the SAME market ---
        # Goal: Assert that the second call is served from the cache.

        # 1. Get data for a single market
        markets_data = seer_subgraph_handler_test.get_markets(
            limit=2, filter_by=FilterBy.OPEN, sort_by=SortBy.HIGHEST_LIQUIDITY
        )
        market_A_data = markets_data[0]

        # 2. Create two separate instances from the exact same market data.
        # They are different objects in memory but share the same `id`.
        market_A_instance_1 = check_not_none(
            SeerAgentMarket.from_data_model_with_subgraph(
                model=market_A_data,
                seer_subgraph=seer_subgraph_handler_test,
                must_have_prices=False,
            )
        )

        market_A_instance_2 = market_A_instance_1.model_copy(deep=True)

        # Sanity check: they are different objects but have the same ID,
        # which is the key for the cache.
        assert market_A_instance_1 is not market_A_instance_2
        assert market_A_instance_1.id == market_A_instance_2.id

        # 3. Call the method on the first instance. This should execute the
        # function body and populate the cache.
        result_1 = market_A_instance_1.has_liquidity()
        assert result_1 is True

        # 4. Assert that the internal method was called for each outcome.
        # The logic is `for outcome in self.outcomes[:-1]`.
        expected_calls = len(market_A_instance_1.outcomes) - 1
        assert mock_has_liquidity_for_outcome.call_count == expected_calls

        # 5. Call the method on the *second* instance. Since it has the same ID,
        # this call should hit the cache.
        # We reset the mock's counter first to ensure we're only measuring the new call.
        mock_has_liquidity_for_outcome.reset_mock()

        result_2 = market_A_instance_2.has_liquidity()
        assert result_2 is True

        # 6. Assert that our internal method was NOT called this time.
        # This proves the result was retrieved from the cache.
        mock_has_liquidity_for_outcome.assert_not_called()

        # --- Test Case 2: Caching with two DIFFERENT markets ---
        # Goal: Assert that different markets have separate cache entries.

        # 1. Get data for a second, different market
        market_B_data = markets_data[1]
        # Ensure the test data is valid and we have two unique markets
        assert market_B_data.id != market_A_data.id

        market_B_instance = check_not_none(
            SeerAgentMarket.from_data_model_with_subgraph(
                model=market_B_data,
                seer_subgraph=seer_subgraph_handler_test,
                must_have_prices=False,
            )
        )

        # 2. Call has_liquidity on the new, different market instance.
        # Since market_B_instance.id is different, it should miss the cache
        # and execute the function body.
        mock_has_liquidity_for_outcome.reset_mock()
        result_B = market_B_instance.has_liquidity()
        assert result_B is True

        # 3. Assert that the internal method was called again for this new market.
        expected_calls_B = len(market_B_instance.outcomes) - 1
        assert mock_has_liquidity_for_outcome.call_count == expected_calls_B
