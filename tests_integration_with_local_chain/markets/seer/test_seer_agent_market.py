from unittest.mock import Mock

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
from prediction_market_agent_tooling.markets.agent_market import (
    FilterBy,
    SortBy,
    ProcessedTradedMarket,
)
from prediction_market_agent_tooling.markets.blockchain_utils import store_trades
from prediction_market_agent_tooling.markets.data_models import (
    TokenAmount,
    ProbabilisticAnswer,
    PlacedTrade,
)
from prediction_market_agent_tooling.markets.seer.seer import SeerAgentMarket
from prediction_market_agent_tooling.markets.seer.seer_subgraph_handler import (
    SeerSubgraphHandler,
)
from prediction_market_agent_tooling.tools.web3_utils import xdai_to_wei

MOCK_APP_DATA = "0x0000000000000000000000000000000000000000000000000000000000000000"  # web3-private-key-ok
MOCK_QUOTE = OrderQuoteResponse(
    quote=OrderParameters(
        buyAmount=TokenAmountCow(str(xdai_to_wei(xdai_type(2)))),  # 0.5 odds
        sellToken=Address("0xabc"),
        buyToken=Address("0xdef"),
        sellAmount=TokenAmountCow("0.5"),
        validTo=1739474477,
        appData=AppDataHash(MOCK_APP_DATA),
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
    agent_market = SeerAgentMarket.from_data_model_with_subgraph(market_data_model)
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


def test_seer_store_trades(
    local_web3: Web3,
    test_keys: APIKeys,
) -> None:
    market_id = "0x02cf28257f0ee4a83fad4b0abc1a82526708f7c2"  # example market
    traded_market = Mock(ProcessedTradedMarket)
    mock_answer = Mock(ProbabilisticAnswer)
    mock_answer.reasoning = "I am a test"
    mock_answer.p_yes = 1
    traded_market.answer = mock_answer
    mock_trade = Mock(PlacedTrade)
    # We use a cowswap order ID which is what the place_bet method from SeerAgentMarket returns.
    mock_trade.id = "0x7d2fec74ec682398793b1e34ad279ef7d859a00820b456c70b27b85209f5229132aaba58de76bdba912fc14fcc11b8aa6227aee967e30ce0"
    mock_trades = [mock_trade]
    traded_market.trades = mock_trades
    test_keys.ENABLE_IPFS_UPLOAD = False

    tx_receipt = store_trades(
        market_id=market_id,
        traded_market=traded_market,
        keys=test_keys,
        agent_name="dummy",
        web3=local_web3,
    )
    assert tx_receipt
