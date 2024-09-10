from unittest.mock import Mock

import pytest

from prediction_market_agent_tooling.deploy.betting_strategy import (
    MaxAccuracyBettingStrategy,
)
from prediction_market_agent_tooling.gtypes import Probability
from prediction_market_agent_tooling.markets.data_models import (
    Position,
    ProbabilisticAnswer,
    TradeType,
    Currency,
    TokenAmount,
)
from prediction_market_agent_tooling.markets.omen.omen import OmenAgentMarket


@pytest.mark.parametrize(
    "estimate_p_yes, market_p_yes, expected_direction",
    [
        (0.6, 0.5, True),
        (0.4, 0.5, False),
    ],
)
def test_answer_decision(
    estimate_p_yes: float, market_p_yes: float, expected_direction: bool
) -> None:
    betting_strategy = MaxAccuracyBettingStrategy()
    direction: bool = betting_strategy.calculate_direction(market_p_yes, estimate_p_yes)
    assert direction == expected_direction


def test_rebalance() -> None:
    strategy = MaxAccuracyBettingStrategy()

    mock_amount = TokenAmount(amount=5, currency=Currency.xDai)
    tiny_amount = TokenAmount(amount=0.0001, currency=Currency.xDai)
    mock_existing_position = Position(
        market_id="0x123",
        amounts={
            OmenAgentMarket.get_outcome_str_from_bool(True): mock_amount,
            OmenAgentMarket.get_outcome_str_from_bool(False): mock_amount,
        },
    )
    mock_answer = ProbabilisticAnswer(p_yes=Probability(0.9), confidence=0.5)
    mock_market = Mock(OmenAgentMarket, wraps=OmenAgentMarket)
    mock_market.get_tiny_bet_amount.return_value = tiny_amount
    mock_market.current_p_yes = 0.5
    mock_market.currency = Currency.xDai
    mock_market.id = "0x123"

    trades = strategy.calculate_trades(mock_existing_position, mock_answer, mock_market)
    # assert 1 buy trade and 1 sell trade
    buy_trade = next(iter([t for t in trades if t.trade_type == TradeType.BUY]))
    assert buy_trade
    assert buy_trade.amount.amount == (mock_amount.amount + tiny_amount.amount)
    sell_trade = next(iter([t for t in trades if t.trade_type == TradeType.SELL]))
    assert sell_trade
    assert sell_trade.amount.amount == (mock_amount.amount)
