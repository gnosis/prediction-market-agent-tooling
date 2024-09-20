import typing as t
from datetime import datetime

import numpy as np
from langfuse import Langfuse
from langfuse.client import TraceWithDetails
from pydantic import BaseModel

from prediction_market_agent_tooling.markets.data_models import (
    ProbabilisticAnswer,
    ResolvedBet,
    Trade,
    TradeType,
)
from prediction_market_agent_tooling.markets.omen.omen import OmenAgentMarket
from prediction_market_agent_tooling.tools.utils import add_utc_timezone_validator


class ProcessMarketTrace(BaseModel):
    timestamp: datetime
    market: OmenAgentMarket
    answer: ProbabilisticAnswer
    trades: list[Trade]

    @property
    def buy_trade(self) -> Trade:
        buy_trades = [t for t in self.trades if t.trade_type == TradeType.BUY]
        if len(buy_trades) == 1:
            return buy_trades[0]
        raise ValueError("No buy trade found")

    @staticmethod
    def from_langfuse_trace(
        trace: TraceWithDetails,
    ) -> t.Optional["ProcessMarketTrace"]:
        market = trace_to_omen_agent_market(trace)
        answer = trace_to_answer(trace)
        trades = trace_to_trades(trace)

        if not market or not answer or not trades:
            return None

        return ProcessMarketTrace(
            market=market,
            answer=answer,
            trades=trades,
            timestamp=trace.timestamp,
        )


class ResolvedBetWithTrace(BaseModel):
    bet: ResolvedBet
    trace: ProcessMarketTrace


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


def trace_to_omen_agent_market(trace: TraceWithDetails) -> OmenAgentMarket | None:
    if not trace.input:
        return None
    if not trace.input["args"]:
        return None
    assert len(trace.input["args"]) == 2 and trace.input["args"][0] == "omen"
    try:
        # If the market model is invalid (e.g. outdated), it will raise an exception
        market = OmenAgentMarket.model_validate(trace.input["args"][1])
        return market
    except Exception:
        return None


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
    bet: ResolvedBet, traces: list[ProcessMarketTrace]
) -> ProcessMarketTrace | None:
    # Filter for traces with the same market id
    traces = [t for t in traces if t.market.id == bet.market_id]

    # Filter for traces with the same bet outcome and amount
    traces_for_bet: list[ProcessMarketTrace] = []
    for t in traces:
        # Cannot use exact comparison due to gas fees
        if t.buy_trade.outcome == bet.outcome and np.isclose(
            t.buy_trade.amount.amount, bet.amount.amount
        ):
            traces_for_bet.append(t)

    if not traces_for_bet:
        return None
    elif len(traces_for_bet) == 1:
        return traces_for_bet[0]
    else:
        # In-case there are multiple traces for the same market, get the closest
        # trace to the bet
        closest_trace_index = get_closest_datetime_from_list(
            add_utc_timezone_validator(bet.created_time),
            [t.timestamp for t in traces_for_bet],
        )

        return traces_for_bet[closest_trace_index]
