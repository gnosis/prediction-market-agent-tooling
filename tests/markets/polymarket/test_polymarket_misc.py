import pytest

from prediction_market_agent_tooling.gtypes import OutcomeStr
from prediction_market_agent_tooling.markets.polymarket.polymarket import (
    PolymarketAgentMarket,
)


def test_get_token_id_for_outcome_yes(
    mock_polymarket_market: PolymarketAgentMarket,
) -> None:
    assert mock_polymarket_market.get_token_id_for_outcome(OutcomeStr("Yes")) == 111


def test_get_token_id_for_outcome_no(
    mock_polymarket_market: PolymarketAgentMarket,
) -> None:
    assert mock_polymarket_market.get_token_id_for_outcome(OutcomeStr("No")) == 222


def test_get_token_id_for_outcome_invalid_raises(
    mock_polymarket_market: PolymarketAgentMarket,
) -> None:
    with pytest.raises(ValueError):
        mock_polymarket_market.get_token_id_for_outcome(OutcomeStr("Maybe"))
