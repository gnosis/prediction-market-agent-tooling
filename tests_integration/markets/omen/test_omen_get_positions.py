import pytest
from web3 import Web3

from prediction_market_agent_tooling.gtypes import OutcomeToken
from prediction_market_agent_tooling.markets.omen.omen import OmenAgentMarket


# TODO: Re-enable once agents are running again and the user below has active
# positions with CoW liquidity. Currently skipped because the agents are shut
# down, so the hardcoded user's positions have no liquidity on CoW, causing
# NoLiquidityAvailableOnCowException on every run.
@pytest.mark.skip(
    reason="Agents are shut down, no CoW liquidity for this user's positions"
)
def test_get_positions_with_live() -> None:
    """
    Check the user's positions against 'market.get_token_balance'

    Also check that `larger_than` and `liquid_only` filters work.

    This is the full integration version that hits live CoW API for USD conversion.
    """
    # Pick a user that has active positions
    user_address = Web3.to_checksum_address(
        "0xf758C18402ddEf2d231911C4C326Aa46510788f0"
    )
    positions = OmenAgentMarket.get_positions(user_id=user_address)
    liquid_positions = OmenAgentMarket.get_positions(
        user_id=user_address,
        liquid_only=True,
    )
    assert len(positions) > len(liquid_positions)

    # Get position id with smallest total amount
    min_position_id = min(positions, key=lambda x: x.total_amount_ot).market_id
    min_amount_position = next(
        position for position in positions if position.market_id == min_position_id
    )

    # Filter for at least 1e-4, because with too low positions,
    # it seems like the graph isn't returning it correctly.
    min_amount_position_ot = max(
        min_amount_position.total_amount_ot, OutcomeToken(0.0001)
    )

    large_positions = OmenAgentMarket.get_positions(
        user_id=user_address, larger_than=min_amount_position_ot
    )
    # Check that the smallest position has been filtered out
    assert all(position.market_id != min_position_id for position in large_positions)
    assert all(
        position.total_amount_ot > min_amount_position_ot
        for position in large_positions
    )

    # Pick a single position to test, otherwise it can be very slow
    position = positions[0]

    market = OmenAgentMarket.get_binary_market(position.market_id)
    for outcome_str in market.outcomes:
        token_balance = market.get_token_balance(
            user_id=user_address,
            outcome=outcome_str,
        )
        if not token_balance:
            # The user has no position in this outcome
            continue
        assert token_balance == position.amounts_ot[outcome_str]
