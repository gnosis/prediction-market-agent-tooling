from unittest.mock import Mock, patch

from eth_pydantic_types import HexStr
from web3 import Web3

from prediction_market_agent_tooling.config import APIKeys
from prediction_market_agent_tooling.gtypes import HexBytes, HexStr, CollateralToken
from prediction_market_agent_tooling.markets.seer.seer import SeerAgentMarket
from prediction_market_agent_tooling.markets.seer.seer_subgraph_handler import (
    SeerSubgraphHandler,
)
from prediction_market_agent_tooling.tools.datetime_utc import DatetimeUTC


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
        agent_market = SeerAgentMarket.from_data_model_with_subgraph(
            model=market,
            seer_subgraph=seer_subgraph_handler_test,
            must_have_prices=False,
        )
        # cow order id 0xcd7f4456ce9756977aa1cca8b1f8eb19f0a9827a6ebfbe2407cda57913831640d0363ccd573163df94b754ca00c0aca2bb66b7486834b44f
        order_date = DatetimeUTC(2025, 5, 25)
        date_diff = DatetimeUTC.now() - order_date
        result = agent_market.have_bet_on_market_since(keys=keys, since=date_diff)
        assert result
