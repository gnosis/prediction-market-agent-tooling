from pathlib import Path
from typing import Any

import dotenv
from eth_typing import HexAddress, HexStr

from examples.monitor.transaction_cache import TransactionBlockCache
from prediction_market_agent_tooling.markets.omen.omen_contracts import OmenConditionalTokenContract
from prediction_market_agent_tooling.markets.omen.omen_subgraph_handler import OmenSubgraphHandler

dotenv.load_dotenv()
import pandas as pd
from langfuse import Langfuse
from pydantic import BaseModel

from prediction_market_agent_tooling.config import APIKeys
from prediction_market_agent_tooling.deploy.betting_strategy import (
    BettingStrategy,
    GuaranteedLossError,
    KellyBettingStrategy,
    ProbabilisticAnswer,
    TradeType,
)
from prediction_market_agent_tooling.markets.data_models import ResolvedBet
from prediction_market_agent_tooling.markets.omen.omen import OmenAgentMarket
from prediction_market_agent_tooling.tools.httpx_cached_client import HttpxCachedClient
from prediction_market_agent_tooling.tools.langfuse_client_utils import (
    ProcessMarketTrace,
    ResolvedBetWithTrace,
    get_trace_for_bet,
    get_traces_for_agent,
)
from prediction_market_agent_tooling.tools.utils import (
    get_private_key_from_gcp_secret,
    utc_datetime,
)


class SimulatedOutcome(BaseModel):
    size: float
    direction: bool
    correct: bool
    profit: float


class MSEProfit(BaseModel):
    p_yes_mse: list[float]
    total_profit: list[float]


def get_outcome_for_trace(
        strategy: BettingStrategy,
        trace: ProcessMarketTrace,
        market_outcome: bool,
        actual_placed_bet: ResolvedBet,
        tx_block_cache: TransactionBlockCache
) -> SimulatedOutcome | None:
    market = trace.market
    answer = trace.answer

    try:
        trades = strategy.calculate_trades(
            existing_position=None,
            answer=ProbabilisticAnswer(
                p_yes=answer.p_yes,
                confidence=answer.confidence,
            ),
            market=market,
        )
    except GuaranteedLossError:
        return None
    # For example, when our predicted p_yes is 95%, but market is already trading at 99%, and we don't have anything to sell, Kelly will yield no trades.
    if not trades:
        return None
    assert (
            len(trades) == 1
    ), f"Should be always one trade if no existing position is given: {trades=}; {answer=}; {market=}"
    assert (
            trades[0].trade_type == TradeType.BUY
    ), "Can only buy without previous position."
    buy_trade = trades[0]
    correct = buy_trade.outcome == market_outcome
    # If not correct, stop early because profit is known.
    if not correct:
        profit = -buy_trade.amount.amount
    else:
        # We use a historical state (by passing in a block_number as arg) to get the correct outcome token balances.
        tx_block_number = tx_block_cache.get_block_number(actual_placed_bet.id)
        market_at_block = OmenSubgraphHandler().get_omen_market_by_market_id(HexAddress(HexStr(market.id)),
                                                                             block_number=tx_block_number)
        omen_agent_market_at_block = OmenAgentMarket.from_data_model(market_at_block)

        received_outcome_tokens = omen_agent_market_at_block.get_buy_token_amount(
            bet_amount=omen_agent_market_at_block.get_bet_amount(buy_trade.amount.amount),
            direction=buy_trade.outcome,
        ).amount
        profit = (
            received_outcome_tokens - buy_trade.amount.amount
            if correct
            else -buy_trade.amount.amount
        )

    # received_outcome_tokens = market.get_buy_token_amount(
    #     bet_amount=market.get_bet_amount(buy_trade.amount.amount),
    #     direction=buy_trade.outcome,
    # ).amount

    return SimulatedOutcome(
        size=buy_trade.amount.amount,
        direction=buy_trade.outcome,
        correct=correct,
        profit=profit,
    )


if __name__ == "__main__":
    output_directory = Path("bet_strategy_benchmark")
    output_directory.mkdir(parents=True, exist_ok=True)

    # Get the private keys for the agents from GCP Secret Manager
    agent_gcp_secret_map = {
        "DeployablePredictionProphetGPT4TurboFinalAgent": "pma-prophetgpt4turbo-final",
        # "DeployablePredictionProphetGPT4TurboPreviewAgent": "pma-prophetgpt4",
        # "DeployablePredictionProphetGPT4oAgent": "pma-prophetgpt3",
        # "DeployablePredictionProphetGPTo1PreviewAgent": "pma-prophet-o1-preview",
        # "DeployablePredictionProphetGPTo1MiniAgent": "pma-prophet-o1-mini",
        # "DeployableOlasEmbeddingOAAgent": "pma-evo-olas-embeddingoa",
        # "DeployableThinkThoroughlyAgent": "pma-think-thoroughly",
        # "DeployableThinkThoroughlyProphetResearchAgent": "pma-think-thoroughly-prophet-research",
        # "DeployableKnownOutcomeAgent": "pma-knownoutcome",
    }

    agent_pkey_map = {
        k: get_private_key_from_gcp_secret(v) for k, v in agent_gcp_secret_map.items()
    }

    # Define strategies we want to test out
    strategies = [
        # MaxAccuracyBettingStrategy(bet_amount=1),
        # MaxAccuracyBettingStrategy(bet_amount=2),
        # MaxAccuracyBettingStrategy(bet_amount=25),
        # KellyBettingStrategy(max_bet_amount=1),
        # KellyBettingStrategy(max_bet_amount=2),
        KellyBettingStrategy(max_bet_amount=5),
        # KellyBettingStrategy(max_bet_amount=25),
        # MaxAccuracyWithKellyScaledBetsStrategy(max_bet_amount=1),
        # MaxAccuracyWithKellyScaledBetsStrategy(max_bet_amount=2),
        # MaxAccuracyWithKellyScaledBetsStrategy(max_bet_amount=25),
        # MaxExpectedValueBettingStrategy(bet_amount=1),
        # MaxExpectedValueBettingStrategy(bet_amount=2),
        # MaxExpectedValueBettingStrategy(bet_amount=5),
        # MaxExpectedValueBettingStrategy(bet_amount=25),
        # KellyBettingStrategy(max_bet_amount=2, max_price_impact=0.01),
        # KellyBettingStrategy(max_bet_amount=2, max_price_impact=0.05),
        # KellyBettingStrategy(max_bet_amount=2, max_price_impact=0.1),
        # KellyBettingStrategy(max_bet_amount=2, max_price_impact=0.15),
        # KellyBettingStrategy(max_bet_amount=2, max_price_impact=0.2),
        # KellyBettingStrategy(max_bet_amount=2, max_price_impact=0.25),
        # KellyBettingStrategy(max_bet_amount=2, max_price_impact=0.3),
        # KellyBettingStrategy(max_bet_amount=2, max_price_impact=0.4),
        # KellyBettingStrategy(max_bet_amount=2, max_price_impact=0.5),
        # KellyBettingStrategy(max_bet_amount=2, max_price_impact=0.6),
        # KellyBettingStrategy(max_bet_amount=2, max_price_impact=0.7),
        # KellyBettingStrategy(max_bet_amount=5, max_price_impact=0.1),
        # KellyBettingStrategy(max_bet_amount=5, max_price_impact=0.15),
        # KellyBettingStrategy(max_bet_amount=5, max_price_impact=0.2),
        # KellyBettingStrategy(max_bet_amount=5, max_price_impact=0.3),
        # KellyBettingStrategy(max_bet_amount=5, max_price_impact=0.4),
        # KellyBettingStrategy(max_bet_amount=5, max_price_impact=0.5),
        # KellyBettingStrategy(max_bet_amount=5, max_price_impact=0.6),
        # KellyBettingStrategy(max_bet_amount=5, max_price_impact=0.7),
        KellyBettingStrategy(max_bet_amount=25, max_price_impact=0.1),
        # KellyBettingStrategy(max_bet_amount=25, max_price_impact=0.2),
        # KellyBettingStrategy(max_bet_amount=25, max_price_impact=0.3),
        # KellyBettingStrategy(max_bet_amount=25, max_price_impact=0.5),
        # KellyBettingStrategy(max_bet_amount=25, max_price_impact=0.7),
    ]

    httpx_client = HttpxCachedClient().get_client()

    overall_md = ""

    strat_mse_profits: dict[str, MSEProfit] = {}
    for strategy in strategies:
        strat_mse_profits[repr(strategy)] = MSEProfit(p_yes_mse=[], total_profit=[])

    print("# Agent Bet vs Simulated Bet Comparison")

    w3 = OmenConditionalTokenContract().get_web3()
    
    tx_block_cache = TransactionBlockCache(web3=w3)

    for agent_name, private_key in agent_pkey_map.items():
        print(f"\n## {agent_name}\n")
        api_keys = APIKeys(BET_FROM_PRIVATE_KEY=private_key)

        # Pick a time after pool token number is stored in OmenAgentMarket
        start_time = utc_datetime(2024, 10, 28)

        langfuse = Langfuse(
            secret_key=api_keys.langfuse_secret_key.get_secret_value(),
            public_key=api_keys.langfuse_public_key,
            host=api_keys.langfuse_host,
            httpx_client=httpx_client,
        )

        traces = get_traces_for_agent(
            agent_name=agent_name,
            trace_name="process_market",
            from_timestamp=start_time,
            has_output=True,
            client=langfuse,
        )
        process_market_traces: list[ProcessMarketTrace] = []
        for trace in traces:
            if process_market_trace := ProcessMarketTrace.from_langfuse_trace(trace):
                process_market_traces.append(process_market_trace)

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
            if not trace:
                print('no trace')
            if trace:
                bets_with_traces.append(ResolvedBetWithTrace(bet=bet, trace=trace))

        print(f"Number of bets since {start_time}: {len(bets_with_traces)}\n")

        if len(bets_with_traces) == 0:
            continue

        if len(bets_with_traces) != len(bets):
            print(
                f"{len(bets) - len(bets_with_traces)} bets do not have a corresponding trace, ignoring them."
            )

        simulations: list[dict[str, Any]] = []
        details = []

        for strategy_idx, strategy in enumerate(strategies):
            # "Born" agent with initial funding, simulate as if he was doing bets one by one.
            starting_balance = 50.0
            agent_balance = starting_balance
            simulated_outcomes: list[SimulatedOutcome] = []

            # ToDo - Can we add the value of tokens that weren't redeemed yet?
            #  Like a portfolio tracking.
            for bet_with_trace in bets_with_traces:
                bet = bet_with_trace.bet
                trace = bet_with_trace.trace
                simulated_outcome = get_outcome_for_trace(
                    strategy=strategy, trace=trace, market_outcome=bet.market_outcome,
                    actual_placed_bet=bet, tx_block_cache=tx_block_cache
                )
                if simulated_outcome is None:
                    continue
                # ToDo - Add new metrics
                simulated_outcomes.append(simulated_outcome)
                agent_balance += simulated_outcome.profit

                details.append(
                    {
                        "url": trace.market.url,
                        "market_p_yes": round(trace.market.current_p_yes, 4),
                        "agent_p_yes": round(trace.answer.p_yes, 4),
                        "agent_conf": round(trace.answer.confidence, 4),
                        "org_bet": round(bet.amount.amount, 4),
                        "sim_bet": round(simulated_outcome.size, 4),
                        "org_dir": bet.outcome,
                        "sim_dir": simulated_outcome.direction,
                        "org_profit": round(bet.profit.amount, 4),
                        "sim_profit": round(simulated_outcome.profit, 4),
                        "timestamp": bet_with_trace.trace.timestamp_datetime,
                    }
                )

            details.sort(key=lambda x: x["sim_profit"], reverse=True)
            pd.DataFrame.from_records(details).to_csv(
                output_directory / f"{agent_name} - {strategy} - all bets.csv",
                index=False,
            )

            sum_squared_errors = 0.0
            for bet_with_trace in bets_with_traces:
                bet = bet_with_trace.bet
                trace = bet_with_trace.trace
                estimated_p_yes = trace.answer.p_yes
                actual_answer = float(bet.market_outcome)
                sum_squared_errors += (estimated_p_yes - actual_answer) ** 2
            p_yes_mse = sum_squared_errors / len(bets_with_traces)
            total_bet_amount = sum([bt.bet.amount.amount for bt in bets_with_traces])
            total_bet_profit = sum([bt.bet.profit.amount for bt in bets_with_traces])
            total_simulated_amount = sum([so.size for so in simulated_outcomes])
            total_simulated_profit = sum([so.profit for so in simulated_outcomes])
            roi = 100 * total_bet_profit / total_bet_amount
            simulated_roi = 100 * total_simulated_profit / total_simulated_amount

            # At the beginning, add also the agent's current strategy.
            if strategy_idx == 0:
                simulations.append(
                    {
                        "strategy": "original",
                        "bet_amount": total_bet_amount,
                        "bet_profit": total_bet_profit,
                        "roi": roi,
                        "p_yes mse": p_yes_mse,
                        # We don't know these for the original run.
                        "start_balance": None,
                        "end_balance": None,
                    }
                )
            else:
                strat_mse_profits[repr(strategy)].p_yes_mse.append(p_yes_mse)
                strat_mse_profits[repr(strategy)].total_profit.append(
                    total_simulated_profit
                )

            simulations.append(
                {
                    "strategy": repr(strategy),
                    "bet_amount": total_simulated_amount,
                    "bet_profit": total_simulated_profit,
                    "roi": simulated_roi,
                    "p_yes mse": p_yes_mse,
                    "start_balance": starting_balance,
                    "end_balance": agent_balance,
                    "daily_return": 123,  # ToDo
                    "annualized_sharpe_ratio": 123,  # ToDo
                    "annualized_volatility": 123,  # ToDo
                }
            )

        simulations_df = pd.DataFrame.from_records(simulations)
        simulations_df.sort_values(by="bet_profit", ascending=False, inplace=True)
        overall_md += (
                f"\n\n## {agent_name}\n\n{len(bets_with_traces)} bets\n\n"
                + simulations_df.to_markdown(index=False)
        )
        # export details per agent
        pd.DataFrame.from_records(details).to_csv(
            output_directory / f"{agent_name}_details.csv"
        )

    print(f"Correlation between p_yes mse and total profit:")
    for strategy_name, mse_profit in strat_mse_profits.items():
        mse = mse_profit.p_yes_mse
        profit = mse_profit.total_profit
        correlation = pd.Series(mse).corr(pd.Series(profit))
        print(f"{strategy_name}: {correlation=}")

    with open(
            output_directory / "match_bets_with_langfuse_traces_overall.md", "w"
    ) as overall_f:
        overall_f.write(overall_md)
