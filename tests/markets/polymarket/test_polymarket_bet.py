import pytest

from prediction_market_agent_tooling.gtypes import CollateralToken, OutcomeStr
from prediction_market_agent_tooling.markets.data_models import Resolution
from prediction_market_agent_tooling.markets.polymarket.data_models import (
    PolymarketBet,
)
from prediction_market_agent_tooling.tools.utils import DatetimeUTC, utcnow


def _make_trade_response(**kwargs: object) -> PolymarketBet:
    defaults = dict(
        id="trade-1",
        taker_order_id="order-1",
        market="0x9deb0baac40648821f96f01339229a422e2f5c877de55dc4dbf981f95a1e709c",
        asset_id="12345",
        side="BUY",
        size=100.0,
        fee_rate_bps=0,
        price=0.6,
        status="MATCHED",
        match_time=utcnow(),
        outcome=OutcomeStr("Yes"),
        event_slug="test-event",
        title="Will it rain tomorrow?",
    )
    defaults.update(kwargs)
    return PolymarketBet(**defaults)  # type: ignore[arg-type]


class TestToBet:
    def test_to_bet_buy(self) -> None:
        trade = _make_trade_response(side="BUY", size=100.0, price=0.6)
        bet = trade.to_bet()

        assert bet.id == "trade-1"
        assert bet.amount == CollateralToken(60.0)
        assert bet.outcome == OutcomeStr("Yes")
        assert bet.created_time == trade.match_time
        assert bet.market_question == "Will it rain tomorrow?"
        assert bet.market_id == trade.market

    def test_to_bet_sell(self) -> None:
        trade = _make_trade_response(side="SELL", size=100.0, price=0.6)
        bet = trade.to_bet()

        assert bet.id == "trade-1"
        assert bet.amount == CollateralToken(60.0)
        assert bet.outcome == OutcomeStr("Yes")


class TestGetProfit:
    @pytest.mark.parametrize(
        "side, outcome, resolution_outcome, expected_profit",
        [
            ("BUY", "Yes", "Yes", 40.0),
            ("BUY", "Yes", "No", -60.0),
            ("SELL", "Yes", "Yes", -40.0),
            ("SELL", "Yes", "No", 60.0),
            ("BUY", "No", "No", 40.0),
            ("BUY", "No", "Yes", -60.0),
        ],
    )
    def test_get_profit(
        self,
        side: str,
        outcome: str,
        resolution_outcome: str,
        expected_profit: float,
    ) -> None:
        trade = _make_trade_response(
            side=side, outcome=OutcomeStr(outcome), size=100.0, price=0.6
        )
        resolution = Resolution.from_answer(OutcomeStr(resolution_outcome))
        profit = trade.get_profit(resolution)
        assert profit == CollateralToken(expected_profit)

    def test_get_profit_invalid_resolution(self) -> None:
        trade = _make_trade_response()
        resolution = Resolution(outcome=None, invalid=True)
        assert trade.get_profit(resolution) == CollateralToken(0)

    def test_get_profit_none_outcome_resolution(self) -> None:
        trade = _make_trade_response()
        resolution = Resolution(outcome=None, invalid=False)
        assert trade.get_profit(resolution) == CollateralToken(0)


class TestToResolvedBet:
    def test_to_generic_resolved_bet_buy_winning(self) -> None:
        trade = _make_trade_response(side="BUY", size=100.0, price=0.6)
        resolution = Resolution.from_answer(OutcomeStr("Yes"))
        resolved_time = utcnow()

        resolved_bet = trade.to_generic_resolved_bet(resolution, resolved_time)

        assert resolved_bet.id == "trade-1"
        assert resolved_bet.amount == CollateralToken(60.0)
        assert resolved_bet.outcome == OutcomeStr("Yes")
        assert resolved_bet.market_outcome == OutcomeStr("Yes")
        assert resolved_bet.is_correct is True
        assert resolved_bet.profit == CollateralToken(40.0)
        assert resolved_bet.resolved_time == resolved_time

    def test_to_generic_resolved_bet_buy_losing(self) -> None:
        trade = _make_trade_response(side="BUY", size=100.0, price=0.6)
        resolution = Resolution.from_answer(OutcomeStr("No"))
        resolved_time = utcnow()

        resolved_bet = trade.to_generic_resolved_bet(resolution, resolved_time)

        assert resolved_bet.is_correct is False
        assert resolved_bet.profit == CollateralToken(-60.0)

    def test_to_generic_resolved_bet_invalid_resolution_raises(self) -> None:
        trade = _make_trade_response()
        resolution = Resolution(outcome=None, invalid=True)
        with pytest.raises(ValueError, match="resolution is invalid"):
            trade.to_generic_resolved_bet(resolution, utcnow())

    def test_to_generic_resolved_bet_none_outcome_raises(self) -> None:
        trade = _make_trade_response()
        resolution = Resolution(outcome=None, invalid=False)
        with pytest.raises(ValueError, match="resolution is invalid"):
            trade.to_generic_resolved_bet(resolution, utcnow())


class TestEdgeCases:
    def test_cost_property(self) -> None:
        trade = _make_trade_response(size=50.0, price=0.8)
        assert trade.cost == CollateralToken(40.0)

    def test_price_near_zero(self) -> None:
        trade = _make_trade_response(size=100.0, price=0.01)
        assert trade.cost == CollateralToken(1.0)

    def test_price_near_one(self) -> None:
        trade = _make_trade_response(size=100.0, price=0.99)
        assert trade.cost == CollateralToken(99.0)

    def test_price_exactly_zero_buy_losing(self) -> None:
        trade = _make_trade_response(side="BUY", size=100.0, price=0.0)
        resolution = Resolution.from_answer(OutcomeStr("No"))
        assert trade.get_profit(resolution) == CollateralToken(0)

    def test_price_exactly_one_buy_winning(self) -> None:
        trade = _make_trade_response(side="BUY", size=100.0, price=1.0)
        resolution = Resolution.from_answer(OutcomeStr("Yes"))
        assert trade.get_profit(resolution) == CollateralToken(0)
