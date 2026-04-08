from datetime import timedelta

import pytest

from prediction_market_agent_tooling.gtypes import USD, OutcomeStr, Probability
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

MOCK_CONDITION_ID_2 = HexBytes(
    "0xaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"  # web3-private-key-ok
)

MOCK_CONDITION_ID_3 = HexBytes(
    "0xbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"  # web3-private-key-ok
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
        question="Will Biden win?",
    )


@pytest.fixture
def mock_gamma_market_2() -> PolymarketGammaMarket:
    return PolymarketGammaMarket(
        conditionId=MOCK_CONDITION_ID_2,
        outcomes='["Yes","No"]',
        outcomePrices="[0.3, 0.7]",
        marketMakerAddress="0xDEF",
        createdAt=utcnow(),
        archived=False,
        clobTokenIds="[333, 444]",
        question="Will Trump win?",
    )


@pytest.fixture
def mock_gamma_market_3() -> PolymarketGammaMarket:
    return PolymarketGammaMarket(
        conditionId=MOCK_CONDITION_ID_3,
        outcomes='["Yes","No"]',
        outcomePrices="[0.1, 0.9]",
        marketMakerAddress="0xGHI",
        createdAt=utcnow(),
        archived=False,
        clobTokenIds="[555, 666]",
        question="Will RFK win?",
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
def mock_multi_market_gamma_response(
    mock_gamma_market: PolymarketGammaMarket,
    mock_gamma_market_2: PolymarketGammaMarket,
    mock_gamma_market_3: PolymarketGammaMarket,
) -> PolymarketGammaResponseDataItem:
    """Event with 3 inner markets (e.g., 'Who wins the election?')"""
    return PolymarketGammaResponseDataItem(
        id="multi-event-1",
        slug="who-wins-election",
        title="Who wins the election?",
        description="Multi-market event",
        archived=False,
        closed=False,
        active=True,
        startDate=utcnow() - timedelta(hours=48),
        endDate=utcnow() + timedelta(hours=48),
        volume=5000.0,
        liquidity=2000.0,
        markets=[mock_gamma_market, mock_gamma_market_2, mock_gamma_market_3],
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
def mock_multi_condition_dict(
    mock_condition_model: ConditionSubgraphModel,
) -> dict[HexBytes, ConditionSubgraphModel]:
    """Condition dict with entries for all 3 inner markets."""
    return {
        MOCK_CONDITION_ID: mock_condition_model,
        MOCK_CONDITION_ID_2: ConditionSubgraphModel(
            id=MOCK_CONDITION_ID_2,
            payoutDenominator=None,
            payoutNumerators=None,
            outcomeSlotCount=2,
            resolutionTimestamp=None,
            questionId=MOCK_QUESTION_ID,
        ),
        MOCK_CONDITION_ID_3: ConditionSubgraphModel(
            id=MOCK_CONDITION_ID_3,
            payoutDenominator=None,
            payoutNumerators=None,
            outcomeSlotCount=2,
            resolutionTimestamp=None,
            questionId=MOCK_QUESTION_ID,
        ),
    }


@pytest.fixture
def mock_polymarket_market() -> PolymarketAgentMarket:
    return PolymarketAgentMarket(
        id=MOCK_CONDITION_ID.to_0x_hex(),
        event_id="1",
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
    )
