from unittest.mock import MagicMock, patch

from prediction_market_agent_tooling.gtypes import USD, OutcomeStr, OutcomeToken
from prediction_market_agent_tooling.markets.polymarket.data_models import (
    PolymarketPositionResponse,
)
from prediction_market_agent_tooling.markets.polymarket.polymarket import (
    PolymarketAgentMarket,
)
from tests.markets.polymarket.conftest import MOCK_CONDITION_ID

MOCK_USER_ID = "0x0000000000000000000000000000000000001234"


def _make_position_response(
    outcome: str, outcome_index: int, size: float, current_value: float
) -> PolymarketPositionResponse:
    return PolymarketPositionResponse(
        slug="test-slug",
        eventSlug="test-event",
        proxyWallet="0x0000000000000000000000000000000000005678",
        asset="test-asset",
        conditionId=MOCK_CONDITION_ID.to_0x_hex(),
        size=size,
        currentValue=current_value,
        cashPnl=0.0,
        redeemable=False,
        outcome=outcome,
        outcomeIndex=outcome_index,
    )


@patch(
    "prediction_market_agent_tooling.markets.polymarket.polymarket.get_user_positions"
)
def test_get_position_with_positions(
    mock_get_positions: MagicMock,
    mock_polymarket_market: PolymarketAgentMarket,
) -> None:
    mock_get_positions.return_value = [
        _make_position_response("Yes", 0, size=10.5, current_value=8.3),
        _make_position_response("No", 1, size=5.0, current_value=3.2),
    ]

    result = mock_polymarket_market.get_position(user_id=MOCK_USER_ID)

    assert result is not None
    assert result.market_id == mock_polymarket_market.id
    assert result.amounts_ot[OutcomeStr("Yes")] == OutcomeToken(10.5)
    assert result.amounts_ot[OutcomeStr("No")] == OutcomeToken(5.0)
    assert result.amounts_potential[OutcomeStr("Yes")] == USD(10.5)
    assert result.amounts_potential[OutcomeStr("No")] == USD(5.0)
    assert result.amounts_current[OutcomeStr("Yes")] == USD(8.3)
    assert result.amounts_current[OutcomeStr("No")] == USD(3.2)


@patch(
    "prediction_market_agent_tooling.markets.polymarket.polymarket.get_user_positions"
)
def test_get_position_filters_by_condition_id(
    mock_get_positions: MagicMock,
    mock_polymarket_market: PolymarketAgentMarket,
) -> None:
    different_condition = (
        "0x0000000000000000000000000000000000000000000000000000000000000000"
    )
    position = _make_position_response("Yes", 0, size=10.0, current_value=8.0)
    position.conditionId = different_condition
    mock_get_positions.return_value = [position]

    result = mock_polymarket_market.get_position(user_id=MOCK_USER_ID)

    assert result is not None
    assert result.amounts_ot[OutcomeStr("Yes")] == OutcomeToken(0)
    assert result.amounts_ot[OutcomeStr("No")] == OutcomeToken(0)
    assert result.amounts_current[OutcomeStr("Yes")] == USD(0)
    assert result.amounts_current[OutcomeStr("No")] == USD(0)
