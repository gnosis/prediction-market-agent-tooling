from collections.abc import Sequence

from prediction_market_agent_tooling.deploy.constants import (
    DOWN_OUTCOME_LOWERCASE_IDENTIFIER,
    NO_OUTCOME_LOWERCASE_IDENTIFIER,
    UP_OUTCOME_LOWERCASE_IDENTIFIER,
    YES_OUTCOME_LOWERCASE_IDENTIFIER,
)
from prediction_market_agent_tooling.markets.agent_market import FilterBy, OutcomeStr
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


def test_get_binary_markets_only(
    seer_subgraph_handler_test: SeerSubgraphHandler,
) -> None:
    """Test that querying for 10 binary markets returns only binary market types."""
    markets = seer_subgraph_handler_test.get_markets(
        limit=10,
        filter_by=FilterBy.NONE,
        include_conditional_markets=True,
        include_categorical_markets=False,
        include_scalar_markets=False,
    )

    assert len(markets) <= 10

    for market in markets:
        # Should be binary markets only
        mid = market.id.hex()
        assert _is_binary_market(
            market.outcomes
        ), f"Market {mid} should be binary, got outcomes: {market.outcomes}"
        assert not _is_scalar_market(
            market.outcomes
        ), f"Market {mid} should not be scalar, got outcomes: {market.outcomes}"


def test_get_scalar_markets_only(
    seer_subgraph_handler_test: SeerSubgraphHandler,
) -> None:
    """Test that querying for 10 scalar markets returns only scalar market types."""
    markets = seer_subgraph_handler_test.get_markets(
        limit=10,
        filter_by=FilterBy.NONE,
        include_conditional_markets=False,
        include_categorical_markets=False,
        include_scalar_markets=True,
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


def test_get_categorical_markets_only(
    seer_subgraph_handler_test: SeerSubgraphHandler,
) -> None:
    """Test that querying for 10 categorical markets returns only categorical market types."""
    markets = seer_subgraph_handler_test.get_markets(
        limit=10,
        filter_by=FilterBy.NONE,
        include_conditional_markets=False,
        include_categorical_markets=True,
        include_scalar_markets=False,
    )

    assert len(markets) <= 10

    for market in markets:
        # Categorical markets should not be scalar or binary
        mid = market.id.hex()
        assert not _is_scalar_market(
            market.outcomes
        ), f"Categorical market {mid} should not be scalar, got outcomes: {market.outcomes}"


def test_exclude_scalar_markets(
    seer_subgraph_handler_test: SeerSubgraphHandler,
) -> None:
    """Test that excluding scalar markets actually excludes them."""
    markets = seer_subgraph_handler_test.get_markets(
        limit=10,
        filter_by=FilterBy.NONE,
        include_conditional_markets=False,
        include_categorical_markets=True,
        include_scalar_markets=False,
    )

    assert len(markets) <= 10

    for market in markets:
        # Should not have scalar markets
        mid = market.id.hex()
        assert not _is_scalar_market(
            market.outcomes
        ), f"Market {mid} should not be scalar when scalar markets are excluded, got outcomes: {market.outcomes}"
