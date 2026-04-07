from prediction_market_agent_tooling.gtypes import (
    USD,
    CollateralToken,
    OutcomeStr,
    Probability,
)
from prediction_market_agent_tooling.markets.data_models import Resolution
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
from tests.markets.polymarket.conftest import (
    MOCK_CONDITION_ID,
    MOCK_CONDITION_ID_2,
    MOCK_CONDITION_ID_3,
)


def test_from_data_model_valid_market(
    mock_gamma_response: PolymarketGammaResponseDataItem,
    mock_condition_dict: dict[HexBytes, ConditionSubgraphModel],
) -> None:
    market = PolymarketAgentMarket.from_data_model(
        mock_gamma_response, mock_condition_dict
    )

    assert market is not None
    assert market.id == MOCK_CONDITION_ID.to_0x_hex()
    assert market.event_id == mock_gamma_response.id
    assert market.question == mock_gamma_response.title
    assert market.outcomes == [OutcomeStr("Yes"), OutcomeStr("No")]
    assert market.probabilities == {
        OutcomeStr("Yes"): Probability(0.6),
        OutcomeStr("No"): Probability(0.4),
    }
    assert market.condition_id == MOCK_CONDITION_ID
    assert market.token_ids == [111, 222]
    assert market.closed_flag_from_polymarket == mock_gamma_response.closed
    assert market.active_flag_from_polymarket == mock_gamma_response.active


def test_from_data_model_missing_prices_returns_none(
    mock_gamma_response: PolymarketGammaResponseDataItem,
    mock_gamma_market: PolymarketGammaMarket,
    mock_condition_dict: dict[HexBytes, ConditionSubgraphModel],
) -> None:
    mock_gamma_market.outcomePrices = None
    response = mock_gamma_response.model_copy(update={"markets": [mock_gamma_market]})

    result = PolymarketAgentMarket.from_data_model(response, mock_condition_dict)

    assert result is None


def test_from_data_model_with_resolved_condition(
    mock_gamma_response: PolymarketGammaResponseDataItem,
    mock_condition_dict: dict[HexBytes, ConditionSubgraphModel],
) -> None:
    market = PolymarketAgentMarket.from_data_model(
        mock_gamma_response, mock_condition_dict
    )

    assert market is not None
    assert market.resolution == Resolution.from_answer(OutcomeStr("Yes"))


def test_from_data_model_no_matching_condition(
    mock_gamma_response: PolymarketGammaResponseDataItem,
) -> None:
    market = PolymarketAgentMarket.from_data_model(
        mock_gamma_response, condition_model_dict={}
    )

    assert market is not None
    assert market.resolution is None


def test_from_data_model_volume_and_liquidity(
    mock_gamma_response: PolymarketGammaResponseDataItem,
    mock_condition_dict: dict[HexBytes, ConditionSubgraphModel],
) -> None:
    market = PolymarketAgentMarket.from_data_model(
        mock_gamma_response, mock_condition_dict
    )

    assert market is not None
    assert mock_gamma_response.volume is not None
    assert mock_gamma_response.liquidity is not None
    assert market.volume == CollateralToken(mock_gamma_response.volume)
    assert market.liquidity_usd == USD(mock_gamma_response.liquidity)


def test_from_data_model_none_liquidity(
    mock_gamma_response: PolymarketGammaResponseDataItem,
    mock_condition_dict: dict[HexBytes, ConditionSubgraphModel],
) -> None:
    response = mock_gamma_response.model_copy(update={"liquidity": None})

    market = PolymarketAgentMarket.from_data_model(response, mock_condition_dict)

    assert market is not None
    assert market.liquidity_usd == USD(0)


# ── Multi-inner-market tests ───────────────────────────────────────────


def test_from_data_model_with_condition_id_selects_correct_inner_market(
    mock_multi_market_gamma_response: PolymarketGammaResponseDataItem,
    mock_multi_condition_dict: dict[HexBytes, ConditionSubgraphModel],
) -> None:
    market = PolymarketAgentMarket.from_data_model(
        mock_multi_market_gamma_response,
        mock_multi_condition_dict,
        condition_id=MOCK_CONDITION_ID_2,
    )

    assert market is not None
    assert market.condition_id == MOCK_CONDITION_ID_2
    assert market.id == MOCK_CONDITION_ID_2.to_0x_hex()
    assert market.event_id == "multi-event-1"
    assert market.token_ids == [333, 444]
    assert market.question == "Will Trump win?"


def test_from_data_model_nonexistent_condition_id_returns_none(
    mock_multi_market_gamma_response: PolymarketGammaResponseDataItem,
    mock_multi_condition_dict: dict[HexBytes, ConditionSubgraphModel],
) -> None:
    nonexistent = HexBytes("0x" + "dd" * 32)
    market = PolymarketAgentMarket.from_data_model(
        mock_multi_market_gamma_response,
        mock_multi_condition_dict,
        condition_id=nonexistent,
    )
    assert market is None


def test_from_data_model_all_returns_all_inner_markets(
    mock_multi_market_gamma_response: PolymarketGammaResponseDataItem,
    mock_multi_condition_dict: dict[HexBytes, ConditionSubgraphModel],
) -> None:
    markets = PolymarketAgentMarket.from_data_model_all(
        mock_multi_market_gamma_response,
        mock_multi_condition_dict,
    )

    assert len(markets) == 3
    condition_ids = {m.condition_id for m in markets}
    assert condition_ids == {
        MOCK_CONDITION_ID,
        MOCK_CONDITION_ID_2,
        MOCK_CONDITION_ID_3,
    }
    assert all(m.event_id == "multi-event-1" for m in markets)


def test_from_data_model_all_unique_ids(
    mock_multi_market_gamma_response: PolymarketGammaResponseDataItem,
    mock_multi_condition_dict: dict[HexBytes, ConditionSubgraphModel],
) -> None:
    markets = PolymarketAgentMarket.from_data_model_all(
        mock_multi_market_gamma_response,
        mock_multi_condition_dict,
    )

    ids = [m.id for m in markets]
    assert len(ids) == len(set(ids))


def test_from_data_model_multi_market_uses_inner_question(
    mock_multi_market_gamma_response: PolymarketGammaResponseDataItem,
    mock_multi_condition_dict: dict[HexBytes, ConditionSubgraphModel],
) -> None:
    """Inner markets with a question field use it instead of the event title."""
    markets = PolymarketAgentMarket.from_data_model_all(
        mock_multi_market_gamma_response,
        mock_multi_condition_dict,
    )

    # First inner market uses its own question field
    first = next(m for m in markets if m.condition_id == MOCK_CONDITION_ID)
    assert first.question == "Will Biden win?"

    # Second inner market has question="Will Trump win?"
    second = next(m for m in markets if m.condition_id == MOCK_CONDITION_ID_2)
    assert second.question == "Will Trump win?"

    # Third inner market has question="Will RFK win?"
    third = next(m for m in markets if m.condition_id == MOCK_CONDITION_ID_3)
    assert third.question == "Will RFK win?"
