import pytest

from prediction_market_agent_tooling.gtypes import OutcomeStr
from prediction_market_agent_tooling.markets.polymarket.data_models import (
    PolymarketGammaMarket,
)
from prediction_market_agent_tooling.tools.utils import utcnow
from tests.markets.polymarket.conftest import MOCK_CONDITION_ID


def _make_gamma_market(**kwargs: object) -> PolymarketGammaMarket:
    defaults = dict(
        conditionId=MOCK_CONDITION_ID,
        outcomes='["Yes","No"]',
        outcomePrices="[0.6, 0.4]",
        marketMakerAddress="0xABC",
        createdAt=utcnow(),
        archived=False,
        clobTokenIds="[111, 222]",
    )
    defaults.update(kwargs)
    return PolymarketGammaMarket(**defaults)  # type: ignore[arg-type]


def test_token_ids_valid_json() -> None:
    market = _make_gamma_market(clobTokenIds="[111, 222]")
    assert market.token_ids == [111, 222]


def test_token_ids_none_raises_value_error() -> None:
    market = _make_gamma_market(clobTokenIds=None)
    with pytest.raises(ValueError, match="Market has no token_ids"):
        market.token_ids


def test_outcomes_list_parsing() -> None:
    market = _make_gamma_market(outcomes='["Yes","No"]')
    assert market.outcomes_list == [OutcomeStr("Yes"), OutcomeStr("No")]


def test_outcomes_list_categorical() -> None:
    market = _make_gamma_market(outcomes='["A","B","C"]')
    assert market.outcomes_list == [OutcomeStr("A"), OutcomeStr("B"), OutcomeStr("C")]


def test_outcome_prices_valid() -> None:
    market = _make_gamma_market(outcomePrices="[0.6, 0.4]")
    assert market.outcome_prices == [0.6, 0.4]


def test_outcome_prices_none_returns_none() -> None:
    market = _make_gamma_market(outcomePrices=None)
    assert market.outcome_prices is None
