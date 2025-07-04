from unittest.mock import patch

from web3 import Web3

from prediction_market_agent_tooling.gtypes import CollateralToken
from prediction_market_agent_tooling.markets.agent_market import FilterBy, SortBy
from prediction_market_agent_tooling.markets.seer.price_manager import PriceManager
from prediction_market_agent_tooling.markets.seer.seer_subgraph_handler import (
    SeerSubgraphHandler,
)


def test_get_price_for_token(seer_subgraph_handler_test: SeerSubgraphHandler) -> None:
    market = seer_subgraph_handler_test.get_markets(
        filter_by=FilterBy.OPEN,
        sort_by=SortBy.HIGHEST_LIQUIDITY,
        limit=1,
        include_categorical_markets=True,
    )[0]

    with patch(
        "prediction_market_agent_tooling.markets.seer.price_manager.get_buy_token_amount_else_raise"
    ) as mock_get_buy_token_amount:
        mock_get_buy_token_amount.return_value = 1

        p = PriceManager.build(market_id=market.id)
        CollateralToken(1)
        other_collateral_token = CollateralToken(2)
        # call it once for filling the cache
        p.get_amount_of_collateral_in_token(
            token=Web3.to_checksum_address(market.wrapped_tokens[0]),
            collateral_exchange_amount=CollateralToken(1),
        )
        # should retrieve the cached value
        p.get_amount_of_collateral_in_token(
            token=Web3.to_checksum_address(market.wrapped_tokens[0]),
            collateral_exchange_amount=CollateralToken(1),
        )
        mock_get_buy_token_amount.assert_called_once()
        # now we call it with a different collateral token
        p.get_amount_of_collateral_in_token(
            token=Web3.to_checksum_address(market.wrapped_tokens[0]),
            collateral_exchange_amount=other_collateral_token,
        )
        assert mock_get_buy_token_amount.call_count == 2
