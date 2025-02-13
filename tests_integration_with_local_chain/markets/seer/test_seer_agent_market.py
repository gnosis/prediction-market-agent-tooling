from unittest.mock import patch, Mock

from cowdao_cowpy.order_book.generated.model import (
    OrderQuoteResponse,
    OrderParameters,
    TokenAmount as TokenAmountCow,
)
from web3 import Web3

from prediction_market_agent_tooling.config import APIKeys
from prediction_market_agent_tooling.gtypes import xdai_type
from prediction_market_agent_tooling.markets.agent_market import FilterBy
from prediction_market_agent_tooling.markets.data_models import TokenAmount
from prediction_market_agent_tooling.markets.seer.seer import SeerAgentMarket
from prediction_market_agent_tooling.markets.seer.seer_subgraph_handler import (
    SeerSubgraphHandler,
)
from prediction_market_agent_tooling.tools.web3_utils import xdai_to_wei

MOCK_QUOTE = OrderQuoteResponse(
    quote=OrderParameters(
        buyAmount=TokenAmountCow(root=str(xdai_to_wei(xdai_type(2)))),  # 0.5 odds
        sellToken="0xabc",
        buyToken="0xdef",
        sellAmount=TokenAmountCow(root="0.5"),
        validTo=" 1739474477",
        appData="0x0000000000000000000000000000000000000000000000000000000000000000",
        feeAmount=TokenAmountCow(root="0.5"),
        kind="buy",
        partiallyFillable=False,
    ),
    expiration="1985-03-10T18:35:18.814523Z",
    verified=False,
)


def test_seer_place_bet(local_web3: Web3, test_keys: APIKeys) -> None:
    with patch(
        "prediction_market_agent_tooling.tools.cow.cow_manager.CowManager.get_quote",
        Mock(return_value=MOCK_QUOTE),
    ), patch(
        "prediction_market_agent_tooling.markets.agent_market.AgentMarket.can_be_traded",
        Mock(return_value=True),
    ), patch(
        "prediction_market_agent_tooling.markets.seer.seer.SeerAgentMarket.has_liquidity_for_outcome",
        Mock(return_value=True),
    ), patch(
        "prediction_market_agent_tooling.tools.cow.cow_manager.CowManager.swap",
    ):
        # We fetch using the subgraph to make sure we get a binary market.
        markets = SeerSubgraphHandler().get_binary_markets(
            filter_by=FilterBy.OPEN, limit=100
        )
        market_data_model = markets[0]
        agent_market = SeerAgentMarket.from_data_model(market_data_model)
        amount = 1

        agent_market.place_bet(
            api_keys=test_keys,
            outcome=True,
            amount=TokenAmount(amount=amount, currency=agent_market.currency),
            auto_deposit=True,
            web3=local_web3,
        )
        # Since we mock the swap call inside `place_bet`, we cannot assert for token balances here. Hence test ends.
