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
from tests.markets.polymarket.conftest import MOCK_CONDITION_ID


def test_from_data_model_valid_market(
    mock_gamma_response: PolymarketGammaResponseDataItem,
    mock_condition_dict: dict[HexBytes, ConditionSubgraphModel],
) -> None:
    market = PolymarketAgentMarket.from_data_model(
        mock_gamma_response, mock_condition_dict, trading_fee_rate=0.1
    )

    assert market is not None
    assert market.id == mock_gamma_response.id
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

    result = PolymarketAgentMarket.from_data_model(
        response, mock_condition_dict, trading_fee_rate=0.1
    )

    assert result is None


def test_from_data_model_with_resolved_condition(
    mock_gamma_response: PolymarketGammaResponseDataItem,
    mock_condition_dict: dict[HexBytes, ConditionSubgraphModel],
) -> None:
    market = PolymarketAgentMarket.from_data_model(
        mock_gamma_response, mock_condition_dict, trading_fee_rate=0.1
    )

    assert market is not None
    assert market.resolution == Resolution.from_answer(OutcomeStr("Yes"))


def test_from_data_model_no_matching_condition(
    mock_gamma_response: PolymarketGammaResponseDataItem,
) -> None:
    market = PolymarketAgentMarket.from_data_model(
        mock_gamma_response, condition_model_dict={}, trading_fee_rate=0.1
    )

    assert market is not None
    assert market.resolution is None


def test_from_data_model_volume_and_liquidity(
    mock_gamma_response: PolymarketGammaResponseDataItem,
    mock_condition_dict: dict[HexBytes, ConditionSubgraphModel],
) -> None:
    market = PolymarketAgentMarket.from_data_model(
        mock_gamma_response, mock_condition_dict, trading_fee_rate=0.1
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

    market = PolymarketAgentMarket.from_data_model(
        response, mock_condition_dict, trading_fee_rate=0.1
    )

    assert market is not None
    assert market.liquidity_usd == USD(0)
