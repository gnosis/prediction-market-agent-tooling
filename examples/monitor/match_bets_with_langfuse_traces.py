from datetime import datetime

from langfuse import Langfuse
from pydantic import BaseModel

from prediction_market_agent_tooling.config import APIKeys
from prediction_market_agent_tooling.markets.data_models import ResolvedBet
from prediction_market_agent_tooling.markets.omen.omen import OmenAgentMarket
from prediction_market_agent_tooling.tools.betting_strategies.kelly_criterion import (
    get_kelly_bet_full,
)
from prediction_market_agent_tooling.tools.langfuse_client_utils import (
    ProcessMarketTrace,
    ResolvedBetWithTrace,
    get_trace_for_bet,
    get_traces_for_agent,
)
from prediction_market_agent_tooling.tools.utils import check_not_none


class KellyBetOutcome(BaseModel):
    size: float
    direction: bool
    correct: bool
    profit: float


def get_kelly_bet_outcome_for_trace(
    trace: ProcessMarketTrace, market_outcome: bool
) -> KellyBetOutcome:
    market = trace.market
    answer = trace.answer
    outcome_token_pool = check_not_none(market.outcome_token_pool)

    kelly_bet = get_kelly_bet_full(
        yes_outcome_pool_size=outcome_token_pool[
            market.get_outcome_str_from_bool(True)
        ],
        no_outcome_pool_size=outcome_token_pool[
            market.get_outcome_str_from_bool(False)
        ],
        estimated_p_yes=answer.p_yes,
        confidence=answer.confidence,
        max_bet=2.0,
        fee=market.fee,
    )
    received_outcome_tokens = market.get_buy_token_amount(
        bet_amount=market.get_bet_amount(kelly_bet.size),
        direction=kelly_bet.direction,
    ).amount
    correct = kelly_bet.direction == market_outcome
    profit = received_outcome_tokens - kelly_bet.size if correct else -kelly_bet.size
    return KellyBetOutcome(
        size=kelly_bet.size,
        direction=kelly_bet.direction,
        correct=correct,
        profit=profit,
    )


if __name__ == "__main__":
    agent_pkey_map = {
        "DeployablePredictionProphetGPT4TurboFinalAgent": "...",
        "DeployablePredictionProphetGPT4TurboPreviewAgent": "...",
        "DeployablePredictionProphetGPT4oAgent": "...",
        "DeployableOlasEmbeddingOAAgent": "...",
        # "DeployableThinkThoroughlyAgent": "...",  # no bets!
        # "DeployableThinkThoroughlyProphetResearchAgent": "...",  # no bets!
        "DeployableKnownOutcomeAgent": "...",
    }
    print("# Agent Bet vs Theoretical Kelly Bet Comparison")
    for agent_name, pkey in agent_pkey_map.items():
        print(f"\n## {agent_name}\n")
        api_keys = APIKeys(BET_FROM_PRIVATE_KEY=pkey)

        # Pick a time after pool token number is stored in OmenAgentMarket
        start_time = datetime(2024, 9, 13)

        langfuse = Langfuse(
            secret_key=api_keys.langfuse_secret_key.get_secret_value(),
            public_key=api_keys.langfuse_public_key,
            host=api_keys.langfuse_host,
        )

        traces = get_traces_for_agent(
            agent_name=agent_name,
            trace_name="process_market",
            from_timestamp=start_time,
            has_output=True,
            client=langfuse,
        )
        process_market_traces = []
        for trace in traces:
            if process_market_trace := ProcessMarketTrace.from_langfuse_trace(trace):
                process_market_traces.append(process_market_trace)

        bets: list[ResolvedBet] = OmenAgentMarket.get_resolved_bets_made_since(
            better_address=api_keys.bet_from_address,
            start_time=start_time,
            end_time=None,
        )
        print(f"All bets: {len(bets)}")

        # All bets should have a trace, but not all traces should have a bet
        # (e.g. if all markets are deemed unpredictable), so iterate over bets
        bets_with_traces: list[ResolvedBetWithTrace] = []
        for bet in bets:
            trace = get_trace_for_bet(bet, process_market_traces)
            if trace:
                bets_with_traces.append(ResolvedBetWithTrace(bet=bet, trace=trace))

        print(f"Matched bets with traces: {len(bets_with_traces)}")

        kelly_bets_outcomes: list[KellyBetOutcome] = []
        for bet_with_trace in bets_with_traces:
            bet = bet_with_trace.bet
            trace = bet_with_trace.trace
            kelly_bet_outcome = get_kelly_bet_outcome_for_trace(
                trace=trace, market_outcome=bet.is_correct
            )
            kelly_bets_outcomes.append(kelly_bet_outcome)

        total_bet_amount = sum([bt.bet.amount.amount for bt in bets_with_traces])
        total_bet_profit = sum([bt.bet.profit.amount for bt in bets_with_traces])
        total_kelly_amount = sum([kbo.size for kbo in kelly_bets_outcomes])
        total_kelly_profit = sum([kbo.profit for kbo in kelly_bets_outcomes])
        roi = 100 * total_bet_profit / total_bet_amount
        kelly_roi = 100 * total_kelly_profit / total_kelly_amount
        print(
            f"Actual Bet: ROI={roi:.2f}%, amount={total_bet_amount:.2f}, profit={total_bet_profit:.2f}"
        )
        print(
            f"Kelly Bet: ROI={kelly_roi:.2f}%, amount={total_kelly_amount:.2f}, profit={total_kelly_profit:.2f}"
        )
