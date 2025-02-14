import pytest
from cowdao_cowpy.order_book.generated.model import (
    Address,
    AppDataHash,
    OrderKind,
    OrderParameters,
    OrderQuoteResponse,
)
from cowdao_cowpy.order_book.generated.model import TokenAmount as TokenAmountCow
from web3 import Web3

from prediction_market_agent_tooling.config import APIKeys
from prediction_market_agent_tooling.gtypes import xdai_type
from prediction_market_agent_tooling.markets.agent_market import FilterBy, SortBy
from prediction_market_agent_tooling.markets.data_models import TokenAmount
from prediction_market_agent_tooling.markets.seer.seer import SeerAgentMarket
from prediction_market_agent_tooling.markets.seer.seer_subgraph_handler import (
    SeerSubgraphHandler,
)
from prediction_market_agent_tooling.tools.web3_utils import xdai_to_wei

MOCK_QUOTE = OrderQuoteResponse(
    quote=OrderParameters(
        buyAmount=TokenAmountCow(str(xdai_to_wei(xdai_type(2)))),  # 0.5 odds
        sellToken=Address("0xabc"),
        buyToken=Address("0xdef"),
        sellAmount=TokenAmountCow("0.5"),
        validTo=1739474477,
        appData=AppDataHash(
            "0x0000000000000000000000000000000000000000000000000000000000000000"
        ),  # web3-private-key-ok
        feeAmount=TokenAmountCow("0.5"),
        kind=OrderKind.buy,
        partiallyFillable=False,
    ),
    expiration="1985-03-10T18:35:18.814523Z",
    verified=False,
)


def test_seer_place_bet(local_web3: Web3, test_keys: APIKeys) -> None:
    # We fetch the market with the highest liquidity because we expect quotes to be available for all outcome tokens.
    markets = SeerSubgraphHandler().get_binary_markets(
        filter_by=FilterBy.OPEN, limit=1, sort_by=SortBy.HIGHEST_LIQUIDITY
    )
    market_data_model = markets[0]
    agent_market = SeerAgentMarket.from_data_model(market_data_model)
    amount = 1
    with pytest.raises(Exception) as e:
        # We expect an exception from Cow since test accounts don't have enough funds.
        agent_market.place_bet(
            api_keys=test_keys,
            outcome=True,
            amount=TokenAmount(amount=amount, currency=agent_market.currency),
            auto_deposit=True,
            web3=local_web3,
        )
    assert "InsufficientBalance" in str(e)
