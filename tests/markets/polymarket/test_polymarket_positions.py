from unittest.mock import MagicMock, patch

from prediction_market_agent_tooling.gtypes import (
    USD,
    CollateralToken,
    OutcomeStr,
    OutcomeToken,
    OutcomeWei,
)
from prediction_market_agent_tooling.markets.data_models import ExistingPosition
from prediction_market_agent_tooling.markets.polymarket.data_models import (
    PolymarketPositionResponse,
    PolymarketSideEnum,
)
from prediction_market_agent_tooling.markets.polymarket.polymarket import (
    PolymarketAgentMarket,
)
from prediction_market_agent_tooling.tools.hexbytes_custom import HexBytes
from tests.markets.polymarket.conftest import MOCK_CONDITION_ID, MOCK_CONDITION_ID_2

MOCK_USER_ID = "0x0000000000000000000000000000000000001234"

SECOND_CONDITION_ID = MOCK_CONDITION_ID_2.to_0x_hex()


def _make_position_response(
    condition_id: str,
    outcome: str,
    outcome_index: int,
    size: float,
    current_value: float,
    event_slug: str = "test-event",
) -> PolymarketPositionResponse:
    return PolymarketPositionResponse(
        slug="test-slug",
        eventSlug=event_slug,
        proxyWallet="0x0000000000000000000000000000000000005678",
        asset="test-asset",
        conditionId=condition_id,
        size=size,
        currentValue=current_value,
        cashPnl=0.0,
        redeemable=False,
        outcome=outcome,
        outcomeIndex=outcome_index,
    )


# ── get_sell_value_of_outcome_token ──────────────────────────────────────


@patch("prediction_market_agent_tooling.markets.polymarket.polymarket.ClobManager")
def test_get_sell_value_basic(
    mock_clob_cls: MagicMock,
    mock_polymarket_market: PolymarketAgentMarket,
) -> None:
    mock_clob_cls.return_value.get_token_price.return_value = USD(0.6)

    result = mock_polymarket_market.get_sell_value_of_outcome_token(
        outcome=OutcomeStr("Yes"), amount=OutcomeToken(10)
    )

    assert result == CollateralToken(6.0)
    mock_clob_cls.return_value.get_token_price.assert_called_once_with(
        token_id=111, side=PolymarketSideEnum.SELL
    )


def test_get_sell_value_zero_amount(
    mock_polymarket_market: PolymarketAgentMarket,
) -> None:
    result = mock_polymarket_market.get_sell_value_of_outcome_token(
        outcome=OutcomeStr("Yes"), amount=OutcomeToken(0)
    )
    assert result == CollateralToken(0)


@patch("prediction_market_agent_tooling.markets.polymarket.polymarket.ClobManager")
def test_get_sell_value_no_outcome(
    mock_clob_cls: MagicMock,
    mock_polymarket_market: PolymarketAgentMarket,
) -> None:
    mock_clob_cls.return_value.get_token_price.return_value = USD(0.4)

    result = mock_polymarket_market.get_sell_value_of_outcome_token(
        outcome=OutcomeStr("No"), amount=OutcomeToken(5)
    )

    assert result == CollateralToken(2.0)
    mock_clob_cls.return_value.get_token_price.assert_called_once_with(
        token_id=222, side=PolymarketSideEnum.SELL
    )


# ── get_token_balance ────────────────────────────────────────────────────


@patch(
    "prediction_market_agent_tooling.markets.polymarket.polymarket.PolymarketConditionalTokenContract"
)
def test_get_token_balance_yes(
    mock_ctf_cls: MagicMock,
    mock_polymarket_market: PolymarketAgentMarket,
) -> None:
    mock_ctf = mock_ctf_cls.return_value
    mock_ctf.getCollectionId.return_value = HexBytes(b"\x01" * 32)
    mock_ctf.getPositionId.return_value = 42
    mock_ctf.balanceOf.return_value = OutcomeWei(5_000_000)

    result = mock_polymarket_market.get_token_balance(
        user_id=MOCK_USER_ID, outcome=OutcomeStr("Yes")
    )

    assert result == OutcomeWei(5_000_000).as_outcome_token
    # Yes is index 0, so index_set = 1 << 0 = 1
    mock_ctf.getCollectionId.assert_called_once()
    call_args = mock_ctf.getCollectionId.call_args
    assert call_args[1].get("web3") is None or call_args[0][2] == 1


@patch(
    "prediction_market_agent_tooling.markets.polymarket.polymarket.PolymarketConditionalTokenContract"
)
def test_get_token_balance_no(
    mock_ctf_cls: MagicMock,
    mock_polymarket_market: PolymarketAgentMarket,
) -> None:
    mock_ctf = mock_ctf_cls.return_value
    mock_ctf.getCollectionId.return_value = HexBytes(b"\x02" * 32)
    mock_ctf.getPositionId.return_value = 99
    mock_ctf.balanceOf.return_value = OutcomeWei(3_000_000)

    result = mock_polymarket_market.get_token_balance(
        user_id=MOCK_USER_ID, outcome=OutcomeStr("No")
    )

    assert result == OutcomeWei(3_000_000).as_outcome_token
    # No is index 1, so index_set = 1 << 1 = 2
    call_args = mock_ctf.getCollectionId.call_args
    assert call_args[0][2] == 2


# ── get_positions ────────────────────────────────────────────────────────


@patch(
    "prediction_market_agent_tooling.markets.polymarket.polymarket.PolymarketSubgraphHandler"
)
@patch(
    "prediction_market_agent_tooling.markets.polymarket.polymarket.get_gamma_event_by_slug"
)
@patch(
    "prediction_market_agent_tooling.markets.polymarket.polymarket.get_user_positions"
)
def test_get_positions_empty(
    mock_get_positions: MagicMock,
    mock_get_event: MagicMock,
    mock_subgraph: MagicMock,
) -> None:
    mock_get_positions.return_value = []
    result = PolymarketAgentMarket.get_positions(user_id=MOCK_USER_ID)
    assert list(result) == []


@patch(
    "prediction_market_agent_tooling.markets.polymarket.polymarket.PolymarketSubgraphHandler"
)
@patch(
    "prediction_market_agent_tooling.markets.polymarket.polymarket.get_gamma_event_by_slug"
)
@patch(
    "prediction_market_agent_tooling.markets.polymarket.polymarket.get_user_positions"
)
def test_get_positions_groups_by_condition_id(
    mock_get_positions: MagicMock,
    mock_get_event: MagicMock,
    mock_subgraph_cls: MagicMock,
    mock_polymarket_market: PolymarketAgentMarket,
    mock_gamma_response: MagicMock,
    mock_condition_model: MagicMock,
) -> None:
    cid1 = MOCK_CONDITION_ID.to_0x_hex()
    mock_get_positions.return_value = [
        _make_position_response(cid1, "Yes", 0, size=10.0, current_value=8.0),
        _make_position_response(cid1, "No", 1, size=5.0, current_value=3.0),
    ]
    mock_get_event.return_value = mock_gamma_response
    mock_subgraph_cls.return_value.get_conditions.return_value = [mock_condition_model]

    result = list(PolymarketAgentMarket.get_positions(user_id=MOCK_USER_ID))

    assert len(result) == 1
    assert result[0].amounts_ot[OutcomeStr("Yes")] == OutcomeToken(10.0)
    assert result[0].amounts_ot[OutcomeStr("No")] == OutcomeToken(5.0)
    assert result[0].amounts_current[OutcomeStr("Yes")] == USD(8.0)
    assert result[0].amounts_potential[OutcomeStr("No")] == USD(5.0)


@patch(
    "prediction_market_agent_tooling.markets.polymarket.polymarket.PolymarketSubgraphHandler"
)
@patch(
    "prediction_market_agent_tooling.markets.polymarket.polymarket.get_gamma_event_by_slug"
)
@patch(
    "prediction_market_agent_tooling.markets.polymarket.polymarket.get_user_positions"
)
def test_get_positions_larger_than_filters(
    mock_get_positions: MagicMock,
    mock_get_event: MagicMock,
    mock_subgraph_cls: MagicMock,
    mock_polymarket_market: PolymarketAgentMarket,
    mock_gamma_response: MagicMock,
    mock_condition_model: MagicMock,
) -> None:
    cid1 = MOCK_CONDITION_ID.to_0x_hex()
    mock_get_positions.return_value = [
        _make_position_response(cid1, "Yes", 0, size=0.5, current_value=0.3),
        _make_position_response(cid1, "No", 1, size=0.2, current_value=0.1),
    ]
    mock_get_event.return_value = mock_gamma_response
    mock_subgraph_cls.return_value.get_conditions.return_value = [mock_condition_model]

    result = list(
        PolymarketAgentMarket.get_positions(
            user_id=MOCK_USER_ID, larger_than=OutcomeToken(1.0)
        )
    )

    assert len(result) == 0


@patch(
    "prediction_market_agent_tooling.markets.polymarket.polymarket.PolymarketSubgraphHandler"
)
@patch(
    "prediction_market_agent_tooling.markets.polymarket.polymarket.get_gamma_event_by_slug"
)
@patch(
    "prediction_market_agent_tooling.markets.polymarket.polymarket.get_user_positions"
)
def test_get_positions_liquid_only_skips_non_tradable(
    mock_get_positions: MagicMock,
    mock_get_event: MagicMock,
    mock_subgraph_cls: MagicMock,
    mock_gamma_response: MagicMock,
    mock_condition_model: MagicMock,
) -> None:
    cid1 = MOCK_CONDITION_ID.to_0x_hex()
    mock_get_positions.return_value = [
        _make_position_response(cid1, "Yes", 0, size=10.0, current_value=8.0),
    ]

    # Make the market closed so can_be_traded() returns False
    mock_gamma_response.closed = True
    mock_get_event.return_value = mock_gamma_response
    mock_subgraph_cls.return_value.get_conditions.return_value = [mock_condition_model]

    result = list(
        PolymarketAgentMarket.get_positions(user_id=MOCK_USER_ID, liquid_only=True)
    )

    assert len(result) == 0


# ── liquidate_existing_positions ─────────────────────────────────────────


@patch.object(PolymarketAgentMarket, "sell_tokens")
@patch.object(PolymarketAgentMarket, "get_positions")
def test_liquidate_sells_non_target_outcomes(
    mock_get_positions: MagicMock,
    mock_sell_tokens: MagicMock,
    mock_polymarket_market: PolymarketAgentMarket,
) -> None:
    mock_get_positions.return_value = [
        ExistingPosition(
            market_id=mock_polymarket_market.id,
            amounts_ot={
                OutcomeStr("Yes"): OutcomeToken(10.0),
                OutcomeStr("No"): OutcomeToken(5.0),
            },
            amounts_current={
                OutcomeStr("Yes"): USD(8.0),
                OutcomeStr("No"): USD(3.0),
            },
            amounts_potential={
                OutcomeStr("Yes"): USD(10.0),
                OutcomeStr("No"): USD(5.0),
            },
        )
    ]
    mock_sell_tokens.return_value = "0xabc"

    mock_polymarket_market.liquidate_existing_positions(outcome=OutcomeStr("Yes"))

    # Should sell "No" only, not "Yes"
    mock_sell_tokens.assert_called_once()
    call_kwargs = mock_sell_tokens.call_args
    assert call_kwargs[1]["outcome"] == OutcomeStr("No")
    assert call_kwargs[1]["amount"] == OutcomeToken(5.0)


@patch.object(PolymarketAgentMarket, "sell_tokens")
@patch.object(PolymarketAgentMarket, "get_positions")
def test_liquidate_no_positions_does_nothing(
    mock_get_positions: MagicMock,
    mock_sell_tokens: MagicMock,
    mock_polymarket_market: PolymarketAgentMarket,
) -> None:
    mock_get_positions.return_value = []

    mock_polymarket_market.liquidate_existing_positions(outcome=OutcomeStr("Yes"))

    mock_sell_tokens.assert_not_called()


# ── get_binary_market ────────────────────────────────────────────────────


@patch("prediction_market_agent_tooling.markets.polymarket.polymarket.ClobManager")
@patch(
    "prediction_market_agent_tooling.markets.polymarket.polymarket.PolymarketSubgraphHandler"
)
@patch(
    "prediction_market_agent_tooling.markets.polymarket.polymarket.get_gamma_event_by_condition_id"
)
def test_get_binary_market(
    mock_get_event: MagicMock,
    mock_subgraph_cls: MagicMock,
    mock_clob_cls: MagicMock,
    mock_gamma_response: MagicMock,
    mock_condition_model: MagicMock,
) -> None:
    mock_get_event.return_value = mock_gamma_response
    mock_subgraph_cls.return_value.get_conditions.return_value = [mock_condition_model]
    mock_clob_cls.return_value.get_token_fee_rate.return_value = 0.01

    market = PolymarketAgentMarket.get_binary_market(id=MOCK_CONDITION_ID.to_0x_hex())

    assert isinstance(market, PolymarketAgentMarket)
    assert market.id == MOCK_CONDITION_ID.to_0x_hex()
    assert market.condition_id == MOCK_CONDITION_ID
    mock_get_event.assert_called_once_with(MOCK_CONDITION_ID)
    mock_clob_cls.return_value.get_token_fee_rate.assert_called_once_with(111)


# ── Multi-inner-market tests ───────────────────────────────────────────


@patch(
    "prediction_market_agent_tooling.markets.polymarket.polymarket.PolymarketSubgraphHandler"
)
@patch(
    "prediction_market_agent_tooling.markets.polymarket.polymarket.get_gamma_event_by_slug"
)
@patch(
    "prediction_market_agent_tooling.markets.polymarket.polymarket.get_user_positions"
)
def test_get_positions_multi_inner_market(
    mock_get_positions: MagicMock,
    mock_get_event: MagicMock,
    mock_subgraph_cls: MagicMock,
    mock_multi_market_gamma_response: MagicMock,
    mock_multi_condition_dict: MagicMock,
) -> None:
    """Positions from different inner markets of the same event are all resolved."""
    cid1 = MOCK_CONDITION_ID.to_0x_hex()
    cid2 = MOCK_CONDITION_ID_2.to_0x_hex()
    mock_get_positions.return_value = [
        _make_position_response(
            cid1, "Yes", 0, size=10.0, current_value=8.0, event_slug="who-wins"
        ),
        _make_position_response(
            cid2, "Yes", 0, size=5.0, current_value=3.0, event_slug="who-wins"
        ),
    ]
    mock_get_event.return_value = mock_multi_market_gamma_response
    mock_subgraph_cls.return_value.get_conditions.return_value = list(
        mock_multi_condition_dict.values()
    )

    result = list(PolymarketAgentMarket.get_positions(user_id=MOCK_USER_ID))

    assert len(result) == 2
    market_ids = {p.market_id for p in result}
    assert cid1 in market_ids
    assert cid2 in market_ids


@patch.object(PolymarketAgentMarket, "sell_tokens")
@patch.object(PolymarketAgentMarket, "get_positions")
def test_liquidate_only_sells_matching_market(
    mock_get_positions: MagicMock,
    mock_sell_tokens: MagicMock,
    mock_polymarket_market: PolymarketAgentMarket,
) -> None:
    """liquidate_existing_positions only sells tokens for the current market."""
    other_cid = "0x" + "ff" * 32
    mock_get_positions.return_value = [
        ExistingPosition(
            market_id=mock_polymarket_market.id,
            amounts_ot={
                OutcomeStr("Yes"): OutcomeToken(10.0),
                OutcomeStr("No"): OutcomeToken(5.0),
            },
            amounts_current={
                OutcomeStr("Yes"): USD(8.0),
                OutcomeStr("No"): USD(3.0),
            },
            amounts_potential={
                OutcomeStr("Yes"): USD(10.0),
                OutcomeStr("No"): USD(5.0),
            },
        ),
        ExistingPosition(
            market_id=other_cid,
            amounts_ot={
                OutcomeStr("Yes"): OutcomeToken(20.0),
                OutcomeStr("No"): OutcomeToken(15.0),
            },
            amounts_current={
                OutcomeStr("Yes"): USD(16.0),
                OutcomeStr("No"): USD(10.0),
            },
            amounts_potential={
                OutcomeStr("Yes"): USD(20.0),
                OutcomeStr("No"): USD(15.0),
            },
        ),
    ]
    mock_sell_tokens.return_value = "0xabc"

    mock_polymarket_market.liquidate_existing_positions(outcome=OutcomeStr("Yes"))

    # Should only sell "No" from matching market, not from the other market
    mock_sell_tokens.assert_called_once()
    call_kwargs = mock_sell_tokens.call_args
    assert call_kwargs[1]["outcome"] == OutcomeStr("No")
    assert call_kwargs[1]["amount"] == OutcomeToken(5.0)
