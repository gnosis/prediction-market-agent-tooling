from datetime import timedelta

import pytest

from prediction_market_agent_tooling.gtypes import USD, OutcomeStr, Probability
from prediction_market_agent_tooling.markets.market_fees import MarketFees
from prediction_market_agent_tooling.markets.polymarket.data_models import (
    PolymarketGammaMarket,
    PolymarketGammaResponseDataItem,
)
from prediction_market_agent_tooling.markets.polymarket.polymarket import (
    PolymarketAgentMarket,
)
from prediction_market_agent_tooling.markets.polymarket.polymarket_subgraph_handler import (
    ConditionSubgraphModel,
)
from prediction_market_agent_tooling.tools.hexbytes_custom import HexBytes
from prediction_market_agent_tooling.tools.utils import utcnow

MOCK_CONDITION_ID = HexBytes(
    "0x9deb0baac40648821f96f01339229a422e2f5c877de55dc4dbf981f95a1e709c"  # web3-private-key-ok
)

MOCK_QUESTION_ID = HexBytes(
    "0xabcdef1234567890abcdef1234567890abcdef1234567890abcdef1234567890"  # web3-private-key-ok
)


@pytest.fixture(scope="module")
def mock_condition_id() -> HexBytes:
    return MOCK_CONDITION_ID


@pytest.fixture
def mock_gamma_market() -> PolymarketGammaMarket:
    return PolymarketGammaMarket(
        conditionId=MOCK_CONDITION_ID,
        outcomes='["Yes","No"]',
        outcomePrices="[0.6, 0.4]",
        marketMakerAddress="0xABC",
        createdAt=utcnow(),
        archived=False,
        clobTokenIds="[111, 222]",
    )


@pytest.fixture
def mock_gamma_response(
    mock_gamma_market: PolymarketGammaMarket,
) -> PolymarketGammaResponseDataItem:
    return PolymarketGammaResponseDataItem(
        id="test-1",
        slug="test-market",
        title="Will GNO go up?",
        description="Test description",
        archived=False,
        closed=False,
        active=True,
        startDate=utcnow() - timedelta(hours=48),
        endDate=utcnow() + timedelta(hours=48),
        volume=1000.0,
        liquidity=500.0,
        markets=[mock_gamma_market],
    )


@pytest.fixture
def mock_condition_model() -> ConditionSubgraphModel:
    return ConditionSubgraphModel(
        id=MOCK_CONDITION_ID,
        payoutDenominator=1,
        payoutNumerators=[1, 0],
        outcomeSlotCount=2,
        resolutionTimestamp=1700000000,
        questionId=MOCK_QUESTION_ID,
    )


@pytest.fixture
def mock_condition_dict(
    mock_condition_model: ConditionSubgraphModel,
) -> dict[HexBytes, ConditionSubgraphModel]:
    return {MOCK_CONDITION_ID: mock_condition_model}


@pytest.fixture
def mock_polymarket_market() -> PolymarketAgentMarket:
    return PolymarketAgentMarket(
        id="1",
        description=None,
        volume=None,
        url="https://polymarket.com/event/test",
        question="Will GNO go up?",
        outcomes=[OutcomeStr("Yes"), OutcomeStr("No")],
        probabilities={
            OutcomeStr("Yes"): Probability(0.6),
            OutcomeStr("No"): Probability(0.4),
        },
        close_time=utcnow() + timedelta(hours=48),
        resolution=None,
        created_time=utcnow() - timedelta(hours=48),
        outcome_token_pool=None,
        condition_id=MOCK_CONDITION_ID,
        liquidity_usd=USD(10),
        token_ids=[111, 222],
        closed_flag_from_polymarket=False,
        active_flag_from_polymarket=True,
        fees=MarketFees(trading_fee_rate=0.1),
    )
