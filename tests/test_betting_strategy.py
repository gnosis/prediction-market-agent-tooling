from datetime import timedelta
from unittest.mock import Mock, patch

import pytest
from web3 import Web3

from prediction_market_agent_tooling.deploy.betting_strategy import (
    BettingStrategy,
    GuaranteedLossError,
    MultiCategoricalMaxAccuracyBettingStrategy,
)
from prediction_market_agent_tooling.gtypes import (
    USD,
    CollateralToken,
    HexAddress,
    HexBytes,
    HexStr,
    OutcomeStr,
    OutcomeToken,
    Probability,
)
from prediction_market_agent_tooling.markets.agent_market import AgentMarket
from prediction_market_agent_tooling.markets.data_models import (
    CategoricalProbabilisticAnswer,
    ExistingPosition,
    TradeType,
)
from prediction_market_agent_tooling.markets.omen.data_models import (
    OMEN_BINARY_MARKET_OUTCOMES,
    OMEN_FALSE_OUTCOME,
    OMEN_TRUE_OUTCOME,
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
    "prob_multi, expected_direction",
    [
        ({"yes": 0.6, "no": 0.4}, OutcomeStr("yes")),
        ({"yes": 0.4, "no": 0.6}, OutcomeStr("no")),
    ],
)
def test_answer_decision(
    prob_multi: dict[OutcomeStr, Probability], expected_direction: OutcomeStr
) -> None:
    betting_strategy = MultiCategoricalMaxAccuracyBettingStrategy(
        max_position_amount=USD(0.1)
    )
    mock_answer = CategoricalProbabilisticAnswer(
        probabilities=prob_multi, confidence=1.0
    )
    # Create a mock market
    mock_market = Mock(spec=AgentMarket)
    # Mock market outcome for probability key (defined in pytest parameterize)
    mock_market.market_outcome_for_probability_key.side_effect = lambda x: x

    direction = betting_strategy.calculate_direction(
        market=mock_market, answer=mock_answer
    )

    assert direction == expected_direction


def mock_outcome_str(x: bool) -> OutcomeStr:
    return OMEN_TRUE_OUTCOME if x else OMEN_FALSE_OUTCOME


@pytest.mark.parametrize("take_profit", [True, False])
def test_rebalance(take_profit: bool) -> None:
    # For simplicity, 1 Token = 1 USD in this test.
    tiny_amount = CollateralToken(0.0001)
    mock_amount = USD(5)
    liquidity_amount = CollateralToken(100)
    mock_existing_position = ExistingPosition(
        market_id="0x123",
        # For simplicity just mock them all as the same amount.
        amounts_current={
            OMEN_TRUE_OUTCOME: mock_amount,
            OMEN_FALSE_OUTCOME: mock_amount,
        },
        amounts_potential={
            OMEN_TRUE_OUTCOME: mock_amount,
            OMEN_FALSE_OUTCOME: mock_amount,
        },
        amounts_ot={
            OMEN_TRUE_OUTCOME: OutcomeToken(mock_amount.value),
            OMEN_FALSE_OUTCOME: OutcomeToken(mock_amount.value),
        },
    )
    buy_token_amount = OutcomeToken(10)
    bet_amount = USD(tiny_amount.value) + mock_existing_position.total_amount_current
    strategy = MultiCategoricalMaxAccuracyBettingStrategy(
        max_position_amount=bet_amount,
        take_profit=take_profit,
    )
    mock_answer = CategoricalProbabilisticAnswer(
        probabilities={
            OMEN_TRUE_OUTCOME: Probability(0.9),
            OMEN_FALSE_OUTCOME: Probability(0.1),
        },
        confidence=0.5,
    )
    mock_market = Mock(OmenAgentMarket, wraps=OmenAgentMarket)
    mock_market.get_liquidity.return_value = liquidity_amount
    mock_market.get_tiny_bet_amount.return_value = tiny_amount
    mock_market.get_buy_token_amount.return_value = buy_token_amount
    mock_market.get_outcome_str_from_bool.side_effect = mock_outcome_str
    mock_market.get_usd_in_collateral_token = lambda x: CollateralToken(x.value)
    mock_market.get_token_in_usd = lambda x: USD(x.value)
    mock_market.get_in_usd = lambda x: USD(x.value)
    mock_market.current_p_yes = 0.5
    mock_market.id = "0x123"
    mock_market.outcomes = [OMEN_TRUE_OUTCOME, OMEN_FALSE_OUTCOME]
    mock_market.market_outcome_for_probability_key.side_effect = lambda x: x

    trades = strategy.calculate_trades(mock_existing_position, mock_answer, mock_market)
    # assert 1 buy trade and 1 sell trade
    assert len(trades) == 2
    # buy trades should come first, sell trades last
    buy_trade = trades[0]
    assert buy_trade.trade_type == TradeType.BUY
    assert buy_trade.amount == mock_amount + USD(tiny_amount.value)
    sell_trade = trades[1]
    assert sell_trade.trade_type == TradeType.SELL
    assert sell_trade.amount == mock_amount


@pytest.mark.parametrize("take_profit", [True, False])
def test_rebalance_with_higher_position_worth(take_profit: bool) -> None:
    # For simplicity, 1 Token = 1 USD in this test.
    tiny_amount = CollateralToken(0.0001)
    mock_amount = USD(5)
    liquidity_amount = CollateralToken(100)
    mock_existing_position = ExistingPosition(
        market_id="0x123",
        # For simplicity just mock them all as the same amount.
        amounts_current={
            OMEN_TRUE_OUTCOME: mock_amount,
            OMEN_FALSE_OUTCOME: USD(0),
        },
        amounts_potential={
            OMEN_TRUE_OUTCOME: mock_amount,
            OMEN_FALSE_OUTCOME: USD(0),
        },
        amounts_ot={
            OMEN_TRUE_OUTCOME: OutcomeToken(mock_amount.value),
            OMEN_FALSE_OUTCOME: OutcomeToken(0),
        },
    )
    buy_token_amount = OutcomeToken(10)
    # Divide the existing position two, to simulate that the existing position increased in value.
    max_position_amount = mock_existing_position.total_amount_current / 2
    strategy = MultiCategoricalMaxAccuracyBettingStrategy(
        max_position_amount=max_position_amount,
        take_profit=take_profit,
    )
    mock_answer = CategoricalProbabilisticAnswer(
        probabilities={
            OMEN_TRUE_OUTCOME: Probability(0.9),
            OMEN_FALSE_OUTCOME: Probability(0.1),
        },
        confidence=0.5,
    )
    mock_market = Mock(OmenAgentMarket, wraps=OmenAgentMarket)
    mock_market.get_liquidity.return_value = liquidity_amount
    mock_market.get_tiny_bet_amount.return_value = tiny_amount
    mock_market.get_buy_token_amount.return_value = buy_token_amount
    mock_market.get_outcome_str_from_bool.side_effect = mock_outcome_str
    mock_market.get_usd_in_collateral_token = lambda x: CollateralToken(x.value)
    mock_market.get_token_in_usd = lambda x: USD(x.value)
    mock_market.get_in_usd = lambda x: USD(x.value)
    mock_market.current_p_yes = 0.5
    mock_market.id = "0x123"
    mock_market.outcomes = [OMEN_TRUE_OUTCOME, OMEN_FALSE_OUTCOME]
    mock_market.market_outcome_for_probability_key.side_effect = lambda x: x

    trades = strategy.calculate_trades(mock_existing_position, mock_answer, mock_market)
    # there should be either 1 sell trade (if not taking profit), or none trades
    assert len(trades) == (1 if take_profit else 0)
    if take_profit:
        sell_trade = trades[0]
        assert sell_trade.trade_type == TradeType.SELL
        assert (
            sell_trade.amount == mock_amount - max_position_amount
        ), "Should take the profit made by increased value of outcome tokens."


@pytest.mark.parametrize(
    "strategy, liquidity, bet_proportion_fee, should_have_trades, should_raise, disable_cap_to_profitable_position",
    [
        (
            MultiCategoricalMaxAccuracyBettingStrategy(max_position_amount=USD(100)),
            1,
            0.02,
            True,
            True,  # Should raise because fee will eat the profit.
            True,  # We need to disabled the profit capping in order to raise.
        ),
        (
            MultiCategoricalMaxAccuracyBettingStrategy(max_position_amount=USD(100)),
            1,
            0.02,
            True,
            False,  # Won't raise because profit capping will trigger.
            False,
        ),
        (
            MultiCategoricalMaxAccuracyBettingStrategy(max_position_amount=USD(100)),
            10,
            0.02,
            True,
            False,  # Should be okay, because liquidity + fee combo is reasonable.
            False,
        ),
        (
            MultiCategoricalMaxAccuracyBettingStrategy(max_position_amount=USD(100)),
            10,
            0.5,
            True,
            True,  # Should raise because fee will eat the profit.
            True,  # We need to disabled the profit capping in order to raise.
        ),
        (
            MultiCategoricalMaxAccuracyBettingStrategy(max_position_amount=USD(100)),
            10,
            0.5,
            False,  # Won't have trades, because the betting strategy won't do any if they aren't profitable.
            False,  # Won't raise because profit capping will trigger.
            False,
        ),
    ],
)
def test_attacking_market(
    strategy: MultiCategoricalMaxAccuracyBettingStrategy,
    liquidity: int,
    bet_proportion_fee: float,
    should_have_trades: bool,
    should_raise: bool,
    disable_cap_to_profitable_position: bool,
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
        probabilities={
            OMEN_TRUE_OUTCOME: Probability(0.5),
            OMEN_FALSE_OUTCOME: Probability(0.5),
        },
        outcome_token_pool={
            OMEN_BINARY_MARKET_OUTCOMES[0]: OutcomeToken(liquidity),
            OMEN_BINARY_MARKET_OUTCOMES[1]: OutcomeToken(liquidity),
        },
        fees=MarketFees.get_zero_fees(bet_proportion=bet_proportion_fee),
    )
    answer = CategoricalProbabilisticAnswer(
        probabilities={
            OMEN_TRUE_OUTCOME: Probability(0.9),
            OMEN_FALSE_OUTCOME: Probability(0.1),
        },
        confidence=1.0,
    )

    def run_test() -> None:
        try:
            trades = strategy.calculate_trades(None, answer, market)
            assert (
                not should_raise
            ), "Should not have raised and return trades normally."
            assert bool(trades) == should_have_trades
        except GuaranteedLossError:
            assert (
                disable_cap_to_profitable_position
            ), "This can not happen if it's enabled."
            assert should_raise, "Should have raise to prevent placing of bet."

    if disable_cap_to_profitable_position:
        with patch.object(
            BettingStrategy,
            "cap_to_profitable_position",
            return_value=strategy.max_position_amount,
        ):
            run_test()
    else:
        with patch.object(
            OmenAgentMarket,
            "get_liquidity",
            return_value=CollateralToken(liquidity),
        ):
            run_test()
