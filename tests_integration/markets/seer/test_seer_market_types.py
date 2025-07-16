from collections.abc import Sequence

from web3.constants import ADDRESS_ZERO

from prediction_market_agent_tooling.deploy.constants import (
    DOWN_OUTCOME_LOWERCASE_IDENTIFIER,
    NO_OUTCOME_LOWERCASE_IDENTIFIER,
    UP_OUTCOME_LOWERCASE_IDENTIFIER,
    YES_OUTCOME_LOWERCASE_IDENTIFIER,
)
from prediction_market_agent_tooling.gtypes import HexAddress, HexStr
from prediction_market_agent_tooling.markets.agent_market import (
    FilterBy,
    OutcomeStr,
    QuestionType,
)
from prediction_market_agent_tooling.markets.seer.seer_subgraph_handler import (
    SeerSubgraphHandler,
)


def _is_scalar_market(outcomes: Sequence[OutcomeStr]) -> bool:
    """Check if market has scalar outcomes (Up/Down + Invalid)"""
    lowercase_outcomes = [o.lower() for o in outcomes]
    has_up = UP_OUTCOME_LOWERCASE_IDENTIFIER in lowercase_outcomes
    has_down = DOWN_OUTCOME_LOWERCASE_IDENTIFIER in lowercase_outcomes
    return has_up and has_down


def _is_binary_market(outcomes: Sequence[OutcomeStr]) -> bool:
    """Check if market has binary outcomes (Yes/No + Invalid)"""
    lowercase_outcomes = [o.lower() for o in outcomes]
    has_yes = YES_OUTCOME_LOWERCASE_IDENTIFIER in lowercase_outcomes
    has_no = NO_OUTCOME_LOWERCASE_IDENTIFIER in lowercase_outcomes
    return has_yes and has_no


def test_conditional_markets_have_parent_address(
    seer_subgraph_handler_test: SeerSubgraphHandler,
) -> None:
    """Test that querying for 10 binary markets returns only binary market types."""
    markets = seer_subgraph_handler_test.get_markets(
        limit=10,
        filter_by=FilterBy.NONE,
        include_conditional_markets=True,
        question_type=QuestionType.BINARY,
    )

    assert len(markets) <= 10

    for market in markets:
        mid = market.id.hex()
        parent_has_address = (
            market.parent_market is None
            or HexAddress(HexStr(market.parent_market.id.hex())) != ADDRESS_ZERO
        )
        assert (
            parent_has_address
        ), f"Market {mid} should not have a parent market, got parent market: {market.parent_market}"


def test_get_scalar_markets_only(
    seer_subgraph_handler_test: SeerSubgraphHandler,
) -> None:
    """Test that querying for 10 scalar markets returns only scalar market types."""
    markets = seer_subgraph_handler_test.get_markets(
        limit=10,
        filter_by=FilterBy.NONE,
        include_conditional_markets=False,
        question_type=QuestionType.SCALAR,
    )

    assert len(markets) <= 10

    for market in markets:
        # Should be scalar markets only
        mid = market.id.hex()
        assert _is_scalar_market(
            market.outcomes
        ), f"Market {mid} should be scalar, got outcomes: {market.outcomes}"
        assert not _is_binary_market(
            market.outcomes
        ), f"Market {mid} should not be binary, got outcomes: {market.outcomes}"
        does_have_parent_market = (
            market.parent_market is not None
            and HexAddress(HexStr(market.parent_market.id.hex())) != ADDRESS_ZERO
        )
        assert (
            not does_have_parent_market
        ), f"Market {mid} should not have a parent market, got parent market: {market.parent_market}"


def test_get_categorical_markets_only(
    seer_subgraph_handler_test: SeerSubgraphHandler,
) -> None:
    """Test that querying for 10 categorical markets returns only categorical market types."""
    markets = seer_subgraph_handler_test.get_markets(
        limit=10,
        filter_by=FilterBy.NONE,
        include_conditional_markets=False,
        question_type=QuestionType.CATEGORICAL,
    )

    for market in markets:
        # Categorical markets should not be scalar or binary
        mid = market.id.hex()
        assert not _is_scalar_market(
            market.outcomes
        ), f"Categorical market {mid} should not be scalar, got outcomes: {market.outcomes}"


def test_binary_markets_only(
    seer_subgraph_handler_test: SeerSubgraphHandler,
) -> None:
    """Test that excluding scalar markets actually excludes them."""
    markets = seer_subgraph_handler_test.get_markets(
        limit=10,
        filter_by=FilterBy.NONE,
        include_conditional_markets=True,
        question_type=QuestionType.BINARY,
    )

    assert len(markets) <= 10

    for market in markets:
        # Should not have scalar markets
        mid = market.id.hex()
        assert not _is_scalar_market(
            market.outcomes
        ), f"Market {mid} should not be scalar when scalar markets are excluded, got outcomes: {market.outcomes}"
