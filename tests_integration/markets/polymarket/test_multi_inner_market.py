from prediction_market_agent_tooling.markets.polymarket.api import (
    get_gamma_event_by_id,
    get_polymarkets_with_pagination,
)
from prediction_market_agent_tooling.markets.polymarket.polymarket import (
    PolymarketAgentMarket,
)
from prediction_market_agent_tooling.markets.polymarket.polymarket_subgraph_handler import (
    PolymarketSubgraphHandler,
)
from prediction_market_agent_tooling.tools.utils import check_not_none


def _find_multi_inner_market_event() -> str:
    """Find a real Polymarket event with multiple inner markets via pagination."""
    items = get_polymarkets_with_pagination(
        limit=200,
        only_binary=False,
    )
    for item in items:
        if item.markets is not None and len(item.markets) > 1:
            return item.id
    raise RuntimeError("No multi-inner-market event found on Polymarket")


def test_fetch_multi_inner_market_event() -> None:
    """Fetch a real multi-inner-market event and verify all inner markets are returned."""
    event_id = _find_multi_inner_market_event()
    event = get_gamma_event_by_id(event_id)

    inner_markets = check_not_none(event.markets)
    assert (
        len(inner_markets) > 1
    ), f"Expected multi-inner-market event, got {len(inner_markets)} inner markets"

    # Collect all condition_ids
    all_condition_ids = [m.conditionId for m in inner_markets]
    assert len(set(all_condition_ids)) == len(
        all_condition_ids
    ), "Each inner market should have a unique condition_id"

    # Fetch conditions from subgraph
    conditions = PolymarketSubgraphHandler().get_conditions(all_condition_ids)
    condition_dict = {c.id: c for c in conditions}

    # Convert to agent markets
    agent_markets = PolymarketAgentMarket.from_data_model_all(
        event, condition_dict, trading_fee_rate=0
    )

    assert (
        len(agent_markets) >= 2
    ), f"Expected at least 2 agent markets, got {len(agent_markets)}"
    assert len(agent_markets) <= len(inner_markets)

    # All should share the same event_id
    assert all(m.event_id == event_id for m in agent_markets)

    # All should have unique market IDs
    ids = [m.id for m in agent_markets]
    assert len(ids) == len(set(ids)), "Market IDs must be unique across inner markets"

    # All should have unique condition_ids
    cids = [m.condition_id for m in agent_markets]
    assert len(cids) == len(set(cids))

    # Each market should have valid probabilities
    for m in agent_markets:
        prob_sum = sum(float(p) for p in m.probabilities.values())
        assert (
            0.99 <= prob_sum <= 1.01
        ), f"Probability sum {prob_sum} out of range for market {m.id}"
        assert len(m.outcomes) >= 2
        assert len(m.token_ids) >= 2


def test_from_data_model_selects_specific_inner_market() -> None:
    """from_data_model with a specific condition_id returns the correct inner market."""
    event_id = _find_multi_inner_market_event()
    event = get_gamma_event_by_id(event_id)

    inner_markets = check_not_none(event.markets)
    assert len(inner_markets) > 1

    # Pick the second inner market
    target = inner_markets[1]
    target_cid = target.conditionId

    conditions = PolymarketSubgraphHandler().get_conditions([target_cid])
    condition_dict = {c.id: c for c in conditions}

    market = PolymarketAgentMarket.from_data_model(
        event, condition_dict, condition_id=target_cid, trading_fee_rate=0
    )

    assert market is not None
    assert market.condition_id == target_cid
    assert market.id == target_cid.to_0x_hex()
    assert market.event_id == event_id
    assert market.token_ids == target.token_ids


def test_get_binary_market_by_condition_id() -> None:
    """get_binary_market can look up a market by its condition_id hex."""
    event_id = _find_multi_inner_market_event()
    event = get_gamma_event_by_id(event_id)

    inner_markets = check_not_none(event.markets)
    # Pick an inner market that has outcome prices so from_data_model won't
    # return None and get_binary_market's check_not_none won't fail.
    target = next(
        (m for m in inner_markets if m.outcome_prices),
        inner_markets[0],
    )
    target_cid = target.conditionId

    market = PolymarketAgentMarket.get_binary_market(id=target_cid.to_0x_hex())

    assert market.condition_id == target_cid
    assert market.id == target_cid.to_0x_hex()
    assert market.event_id == event_id
