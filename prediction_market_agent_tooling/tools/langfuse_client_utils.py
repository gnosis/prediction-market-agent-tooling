from datetime import datetime

from langfuse import Langfuse
from langfuse.client import TraceWithDetails

from prediction_market_agent_tooling.loggers import logger
from prediction_market_agent_tooling.markets.data_models import (
    ProbabilisticAnswer,
    ResolvedBet,
    Trade,
)
from prediction_market_agent_tooling.markets.omen.omen import OmenAgentMarket
from prediction_market_agent_tooling.tools.utils import add_utc_timezone_validator


def get_traces_for_agent(
    agent_name: str,
    trace_name: str,
    from_timestamp: datetime,
    has_output: bool,
    client: Langfuse,
) -> list[TraceWithDetails]:
    """
    Fetch agent traces using pagination
    """
    page = 1  # index starts from 1
    all_agent_traces = []
    while True:
        traces = client.fetch_traces(
            name=trace_name,
            limit=100,
            page=page,
            from_timestamp=from_timestamp,
        )
        if not traces.data:
            break
        page += 1

        agent_traces = [
            t
            for t in traces.data
            if t.session_id is not None and agent_name in t.session_id
        ]
        if has_output:
            agent_traces = [t for t in agent_traces if t.output is not None]
        all_agent_traces.extend(agent_traces)
    return all_agent_traces


def trace_to_omen_agent_market(trace: TraceWithDetails) -> OmenAgentMarket:
    assert trace.input is not None, "Trace input is None"
    assert trace.input["args"] is not None, "Trace input args is None"
    assert len(trace.input["args"]) == 2 and trace.input["args"][0] == "omen"
    return OmenAgentMarket.model_validate(trace.input["args"][1])


def trace_to_answer(trace: TraceWithDetails) -> ProbabilisticAnswer:
    assert trace.output is not None, "Trace output is None"
    assert trace.output["answer"] is not None, "Trace output result is None"
    return ProbabilisticAnswer.model_validate(trace.output["answer"])


def trace_to_trades(trace: TraceWithDetails) -> list[Trade]:
    assert trace.output is not None, "Trace output is None"
    assert trace.output["trades"] is not None, "Trace output trades is None"
    return [Trade.model_validate(t) for t in trace.output["trades"]]


def get_closest_datetime_from_list(
    ref_datetime: datetime, datetimes: list[datetime]
) -> int:
    """Get the index of the closest datetime to the reference datetime"""
    if len(datetimes) == 1:
        return 0

    closest_datetime = min(datetimes, key=lambda dt: abs(dt - ref_datetime))
    return datetimes.index(closest_datetime)


def get_trace_for_bet(
    bet: ResolvedBet, traces: list[TraceWithDetails]
) -> TraceWithDetails | None:
    # Get traces with the same market id
    traces_for_bet = [
        t for t in traces if trace_to_omen_agent_market(t).id == bet.market_id
    ]

    # In-case there are multiple traces for the same market, get the closest trace to the bet
    closest_trace_index = get_closest_datetime_from_list(
        add_utc_timezone_validator(bet.created_time),
        [t.timestamp for t in traces_for_bet],
    )
    # Sanity check - the trace should be after the bet
    if traces_for_bet[closest_trace_index].timestamp < add_utc_timezone_validator(
        bet.created_time
    ):
        logger.warning(
            f"No trace for bet on market {bet.market_id} at time {bet.created_time} found"
        )
        return None

    return traces_for_bet[closest_trace_index]
