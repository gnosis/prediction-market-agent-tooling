import typing as t

import numpy as np
from langfuse import Langfuse
from langfuse.client import TraceWithDetails
from pydantic import BaseModel

from prediction_market_agent_tooling.loggers import logger
from prediction_market_agent_tooling.markets.data_models import (
    PlacedTrade,
    CategoricalProbabilisticAnswer,
    ResolvedBet,
    TradeType,
)
from prediction_market_agent_tooling.markets.omen.omen import OmenAgentMarket
from prediction_market_agent_tooling.markets.omen.omen_constants import (
    WRAPPED_XDAI_CONTRACT_ADDRESS,
)
from prediction_market_agent_tooling.tools.utils import DatetimeUTC


class ProcessMarketTrace(BaseModel):
    timestamp: int
    market: OmenAgentMarket
    answer: CategoricalProbabilisticAnswer
    trades: list[PlacedTrade]

    @property
    def timestamp_datetime(self) -> DatetimeUTC:
        return DatetimeUTC.to_datetime_utc(self.timestamp)

    @property
    def buy_trade(self) -> PlacedTrade | None:
        buy_trades = [t for t in self.trades if t.trade_type == TradeType.BUY]
        if len(buy_trades) > 1:
            raise ValueError("Unhandled logic, check it outm please!")
        return buy_trades[0] if buy_trades else None

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
            timestamp=int(trace.timestamp.timestamp()),
        )


class ResolvedBetWithTrace(BaseModel):
    bet: ResolvedBet
    trace: ProcessMarketTrace


def get_traces_for_agent(
    agent_name: str,
    trace_name: str,
    from_timestamp: DatetimeUTC,
    has_output: bool,
    client: Langfuse,
    to_timestamp: DatetimeUTC | None = None,
    tags: str | list[str] | None = None,
) -> list[TraceWithDetails]:
    """
    Fetch agent traces using pagination
    """
    total_pages = -1
    page = 1  # index starts from 1
    all_agent_traces = []
    while True:
        logger.debug(f"Fetching Langfuse page {page} / {total_pages}.")
        traces = client.fetch_traces(
            name=trace_name,
            limit=100,
            page=page,
            from_timestamp=from_timestamp,
            to_timestamp=to_timestamp,
            tags=tags,
        )
        if not traces.data:
            break
        page += 1
        total_pages = traces.meta.total_pages

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
        logger.warning(f"No input in the trace: {trace}")
        return None
    if not trace.input["args"]:
        logger.warning(f"No args in the trace: {trace}")
        return None
    assert len(trace.input["args"]) == 2 and trace.input["args"][0] == "omen"
    try:
        # If the market model is invalid (e.g. outdated), it will raise an exception
        market = OmenAgentMarket.model_validate(trace.input["args"][1])
        return market
    except Exception as e:
        logger.warning(f"Market not parsed from langfuse because: {e}")
        return None


def trace_to_answer(trace: TraceWithDetails) -> CategoricalProbabilisticAnswer:
    assert trace.output is not None, "Trace output is None"
    assert trace.output["answer"] is not None, "Trace output result is None"
    return CategoricalProbabilisticAnswer.model_validate(trace.output["answer"])


def trace_to_trades(trace: TraceWithDetails) -> list[PlacedTrade]:
    assert trace.output is not None, "Trace output is None"
    assert trace.output["trades"] is not None, "Trace output trades is None"
    return [PlacedTrade.model_validate(t) for t in trace.output["trades"]]


def get_closest_datetime_from_list(
    ref_datetime: DatetimeUTC, datetimes: list[DatetimeUTC]
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
        if (
            t.market.collateral_token_contract_address_checksummed
            not in WRAPPED_XDAI_CONTRACT_ADDRESS
        ):
            # TODO: We need to compute bet amount token in USD here, but at the time of bet placement!
            logger.warning(
                "This currently works only for WXDAI markets, because we need to compare against USD value."
            )
            continue
        # Cannot use exact comparison due to gas fees
        if (
            t.buy_trade
            and t.buy_trade.outcome == bet.outcome
            and np.isclose(t.buy_trade.amount.value, bet.amount.value)
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
            bet.created_time,
            [t.timestamp_datetime for t in traces_for_bet],
        )

        # Sanity check: Let's say the upper bound for time between
        # `agent.process_market` being called and the bet being placed is 20
        # minutes
        candidate_trace = traces_for_bet[closest_trace_index]
        if (
            abs(candidate_trace.timestamp_datetime - bet.created_time).total_seconds()
            > 1200
        ):
            logger.info(
                f"Closest trace to bet has timestamp {candidate_trace.timestamp}, "
                f"but bet was created at {bet.created_time}. Not matching"
            )
            return None

        return traces_for_bet[closest_trace_index]
