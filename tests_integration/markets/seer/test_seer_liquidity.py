from prediction_market_agent_tooling.markets.agent_market import (
    FilterBy,
    QuestionType,
    SortBy,
)
from prediction_market_agent_tooling.markets.seer.seer import SeerAgentMarket
from prediction_market_agent_tooling.markets.seer.seer_subgraph_handler import (
    SeerSubgraphHandler,
)
from prediction_market_agent_tooling.tools.utils import check_not_none


def test_get_liquidity(seer_subgraph_handler_test: SeerSubgraphHandler) -> None:
    liquid_market = seer_subgraph_handler_test.get_markets(
        limit=1,
        sort_by=SortBy.HIGHEST_LIQUIDITY,
        filter_by=FilterBy.OPEN,
        question_type=QuestionType.BINARY,
        include_conditional_markets=False,
    )[0]
    # We expect outcomes to have been minted
    agent_market = check_not_none(
        SeerAgentMarket.from_data_model_with_subgraph(
            model=liquid_market,
            seer_subgraph=seer_subgraph_handler_test,
            must_have_prices=True,
        )
    )
    print(agent_market.get_liquidity())
    assert liquid_market.outcomes_supply > 0
    assert agent_market.has_liquidity()
