from datetime import datetime

from langfuse import Langfuse
from web3 import Web3

from prediction_market_agent_tooling.config import APIKeys
from prediction_market_agent_tooling.markets.data_models import ResolvedBet
from prediction_market_agent_tooling.markets.omen.omen import OmenAgentMarket
from prediction_market_agent_tooling.tools.langfuse_client_utils import (
    ProcessMarketTrace,
    ResolvedBetWithTrace,
    get_trace_for_bet,
    get_traces_for_agent,
)

if __name__ == "__main__":
    api_keys = APIKeys()
    assert api_keys.bet_from_address == Web3.to_checksum_address(
        "0xA8eFa5bb5C6ad476c9E0377dbF66cC41CB6D5bdD"  # prophet_gpt4_final
    )
    start_time = datetime(2024, 9, 13)
    langfuse = Langfuse(
        secret_key=api_keys.langfuse_secret_key.get_secret_value(),
        public_key=api_keys.langfuse_public_key,
        host=api_keys.langfuse_host,
    )

    traces = get_traces_for_agent(
        agent_name="DeployablePredictionProphetGPT4TurboFinalAgent",
        trace_name="process_market",
        from_timestamp=start_time,
        has_output=True,
        client=langfuse,
    )
    print(f"All traces: {len(traces)}")
    process_market_traces = []
    for trace in traces:
        if process_market_trace := ProcessMarketTrace.from_langfuse_trace(trace):
            process_market_traces.append(process_market_trace)
    print(f"All process_market_traces: {len(process_market_traces)}")

    bets: list[ResolvedBet] = OmenAgentMarket.get_resolved_bets_made_since(
        better_address=api_keys.bet_from_address,
        start_time=start_time,
        end_time=None,
    )

    # All bets should have a trace, but not all traces should have a bet
    # (e.g. if all markets are deemed unpredictable), so iterate over bets
    bets_with_traces: list[ResolvedBetWithTrace] = []
    for bet in bets:
        trace = get_trace_for_bet(bet, process_market_traces)
        if trace:
            bets_with_traces.append(ResolvedBetWithTrace(bet=bet, trace=trace))

    print(f"Number of bets since {start_time}: {len(bets_with_traces)}")
    if len(bets_with_traces) != len(bets):
        raise ValueError(
            f"{len(bets) - len(bets_with_traces)} bets do not have a corresponding trace"
        )
