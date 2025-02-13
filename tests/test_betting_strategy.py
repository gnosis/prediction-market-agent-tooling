from datetime import timedelta
from unittest.mock import Mock

import pytest
from web3 import Web3

from prediction_market_agent_tooling.deploy.betting_strategy import (
    BettingStrategy,
    MaxAccuracyBettingStrategy,
)
from prediction_market_agent_tooling.gtypes import (
    HexAddress,
    HexBytes,
    HexStr,
    Probability,
    OutcomeStr,
)
from prediction_market_agent_tooling.markets.data_models import (
    Currency,
    Position,
    ProbabilisticAnswer,
    TokenAmount,
    TradeType,
)
from prediction_market_agent_tooling.markets.omen.data_models import (
    OMEN_BINARY_MARKET_OUTCOMES,
    OMEN_TRUE_OUTCOME,
    OMEN_FALSE_OUTCOME,
)
from prediction_market_agent_tooling.markets.omen.omen import (
    Condition,
    MarketFees,
    OmenAgentMarket,
)
from prediction_market_agent_tooling.markets.omen.omen_contracts import (
    WrappedxDaiContract,
)
from prediction_market_agent_tooling.tools.utils import utcnow


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
    betting_strategy = MaxAccuracyBettingStrategy(bet_amount=0.1)
    direction: bool = betting_strategy.calculate_direction(market_p_yes, estimate_p_yes)
    assert direction == expected_direction


def test_rebalance() -> None:
    tiny_amount = TokenAmount(amount=0.0001, currency=Currency.xDai)
    mock_amount = TokenAmount(amount=5, currency=Currency.xDai)
    liquidity_amount = TokenAmount(amount=100, currency=Currency.xDai)
    mock_existing_position = Position(
        market_id="0x123",
        amounts={
            OutcomeStr(OMEN_TRUE_OUTCOME): mock_amount,
            OutcomeStr(OMEN_FALSE_OUTCOME): mock_amount,
        },
    )
    bet_amount = tiny_amount.amount + mock_existing_position.total_amount.amount
    buy_token_amount = TokenAmount(amount=10, currency=Currency.xDai)
    strategy = MaxAccuracyBettingStrategy(bet_amount=bet_amount)
    mock_answer = ProbabilisticAnswer(p_yes=Probability(0.9), confidence=0.5)
    mock_market = Mock(OmenAgentMarket, wraps=OmenAgentMarket)
    mock_market.get_liquidity.return_value = liquidity_amount
    mock_market.get_tiny_bet_amount.return_value = tiny_amount
    mock_market.get_buy_token_amount.return_value = buy_token_amount
    mock_market.current_p_yes = 0.5
    mock_market.currency = Currency.xDai
    mock_market.id = "0x123"

    trades = strategy.calculate_trades(mock_existing_position, mock_answer, mock_market)
    # assert 1 buy trade and 1 sell trade
    assert len(trades) == 2
    # buy trades should come first, sell trades last
    buy_trade = trades[0]
    assert buy_trade.trade_type == TradeType.BUY
    assert buy_trade.amount.amount == (mock_amount.amount + tiny_amount.amount)
    sell_trade = trades[1]
    assert sell_trade.trade_type == TradeType.SELL
    assert sell_trade.amount.amount == mock_amount.amount


@pytest.mark.parametrize(
    "strategy, liquidity, bet_proportion_fee, should_raise",
    [
        (
            MaxAccuracyBettingStrategy(bet_amount=100),
            1,
            0.02,
            True,  # Should raise because fee will eat the profit.
        ),
        (
            MaxAccuracyBettingStrategy(bet_amount=100),
            10,
            0.02,
            False,  # Should be okay, because liquidity + fee combo is reasonable.
        ),
        (
            MaxAccuracyBettingStrategy(bet_amount=100),
            10,
            0.5,
            True,  # Should raise because fee will eat the profit.
        ),
    ],
)
def test_attacking_market(
    strategy: BettingStrategy,
    liquidity: float,
    bet_proportion_fee: float,
    should_raise: bool,
) -> None:
    """
    Test if markets with unreasonably low liquidity and/or high fees won't put agent into immediate loss.
    """
    market = OmenAgentMarket(
        id="0x0",
        question="How you doing?",
        outcomes=OMEN_BINARY_MARKET_OUTCOMES,
        resolution=None,
        url="",
        volume=None,
        creator=HexAddress(HexStr("0x0")),
        collateral_token_contract_address_checksummed=WrappedxDaiContract().address,
        market_maker_contract_address_checksummed=Web3.to_checksum_address(
            "0x0000000000000000000000000000000000000001"
        ),
        condition=Condition(
            id=HexBytes("0x0"), outcomeSlotCount=len(OMEN_BINARY_MARKET_OUTCOMES)
        ),
        finalized_time=None,
        created_time=utcnow(),
        close_time=utcnow() + timedelta(days=3),
        current_p_yes=Probability(0.5),
        outcome_token_pool={
            OMEN_BINARY_MARKET_OUTCOMES[0]: liquidity,
            OMEN_BINARY_MARKET_OUTCOMES[1]: liquidity,
        },
        fees=MarketFees.get_zero_fees(bet_proportion=bet_proportion_fee),
    )
    answer = ProbabilisticAnswer(p_yes=Probability(0.9), confidence=1.0)

    try:
        trades = strategy.calculate_trades(None, answer, market)
        assert not should_raise, "Should not have raised and return trades normally."
        assert trades, "No trades available."
    except Exception:
        assert should_raise, "Should have raise to prevent placing of bet."
