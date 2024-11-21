import typing as t
from pathlib import Path

import optuna
import pandas as pd
from eth_typing import HexAddress, HexStr
from langfuse import Langfuse
from pydantic import BaseModel
from sklearn.model_selection import TimeSeriesSplit

from prediction_market_agent_tooling.config import APIKeys
from prediction_market_agent_tooling.deploy.betting_strategy import (
    BettingStrategy,
    GuaranteedLossError,
    KellyBettingStrategy,
    MaxAccuracyBettingStrategy,
    MaxAccuracyWithKellyScaledBetsStrategy,
    MaxExpectedValueBettingStrategy,
    ProbabilisticAnswer,
    TradeType,
)
from prediction_market_agent_tooling.markets.data_models import (
    ResolvedBet,
    SimulatedBetDetail,
    SimulatedLifetimeDetail,
)
from prediction_market_agent_tooling.markets.omen.omen import OmenAgentMarket
from prediction_market_agent_tooling.markets.omen.omen_contracts import (
    OmenConditionalTokenContract,
)
from prediction_market_agent_tooling.markets.omen.omen_subgraph_handler import (
    OmenSubgraphHandler,
)
from prediction_market_agent_tooling.monitor.financial_metrics.financial_metrics import (
    SharpeRatioCalculator,
)
from prediction_market_agent_tooling.tools.google_utils import (
    get_private_key_from_gcp_secret,
)
from prediction_market_agent_tooling.tools.httpx_cached_client import HttpxCachedClient
from prediction_market_agent_tooling.tools.langfuse_client_utils import (
    ProcessMarketTrace,
    ResolvedBetWithTrace,
    get_trace_for_bet,
    get_traces_for_agent,
)
from prediction_market_agent_tooling.tools.transaction_cache import (
    TransactionBlockCache,
)
from prediction_market_agent_tooling.tools.utils import check_not_none, utc_datetime

optuna.logging.set_verbosity(optuna.logging.WARNING)


class SimulatedOutcome(BaseModel):
    size: float
    direction: bool
    correct: bool
    profit: float


def get_outcome_for_trace(
    strategy: BettingStrategy,
    trace: ProcessMarketTrace,
    market_outcome: bool,
    actual_placed_bet: ResolvedBet,
    tx_block_cache: TransactionBlockCache,
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
        market_at_block = OmenSubgraphHandler().get_omen_market_by_market_id(
            HexAddress(HexStr(market.id)), block_number=tx_block_number
        )
        omen_agent_market_at_block = OmenAgentMarket.from_data_model(market_at_block)

        received_outcome_tokens = omen_agent_market_at_block.get_buy_token_amount(
            bet_amount=omen_agent_market_at_block.get_bet_amount(
                buy_trade.amount.amount
            ),
            direction=buy_trade.outcome,
        ).amount
        profit = received_outcome_tokens - buy_trade.amount.amount

    return SimulatedOutcome(
        size=buy_trade.amount.amount,
        direction=buy_trade.outcome,
        correct=correct,
        profit=profit,
    )


def calc_metrics(
    bets: list[ResolvedBetWithTrace],
    strategy: BettingStrategy,
    tx_block_cache: TransactionBlockCache,
) -> tuple[list[SimulatedBetDetail], SimulatedLifetimeDetail]:
    per_bet_details: list[SimulatedBetDetail] = []
    simulated_outcomes: list[SimulatedOutcome] = []

    for bet_with_trace in bets:
        simulated_outcome = get_outcome_for_trace(
            strategy=strategy,
            trace=bet_with_trace.trace,
            market_outcome=bet_with_trace.bet.market_outcome,
            actual_placed_bet=bet_with_trace.bet,
            tx_block_cache=tx_block_cache,
        )
        simulated_outcome = get_outcome_for_trace(
            strategy=strategy,
            trace=bet_with_trace.trace,
            market_outcome=bet_with_trace.bet.market_outcome,
            actual_placed_bet=bet_with_trace.bet,
            tx_block_cache=tx_block_cache,
        )
        if simulated_outcome is None:
            continue
        simulated_outcomes.append(simulated_outcome)
        simulation_detail = SimulatedBetDetail(
            strategy=repr(strategy),
            url=bet_with_trace.trace.market.url,
            market_p_yes=round(bet_with_trace.trace.market.current_p_yes, 4),
            agent_p_yes=round(bet_with_trace.trace.answer.p_yes, 4),
            agent_conf=round(bet_with_trace.trace.answer.confidence, 4),
            org_bet=round(bet_with_trace.bet.amount.amount, 4),
            sim_bet=round(simulated_outcome.size, 4),
            org_dir=bet_with_trace.bet.outcome,
            sim_dir=simulated_outcome.direction,
            org_profit=round(bet_with_trace.bet.profit.amount, 4),
            sim_profit=round(simulated_outcome.profit, 4),
            timestamp=bet_with_trace.trace.timestamp_datetime,
        )
        per_bet_details.append(simulation_detail)

    # Financial analysis
    calc = SharpeRatioCalculator(details=per_bet_details)
    sharpe_output_simulation = calc.calculate_annual_sharpe_ratio()
    sharpe_output_original = calc.calculate_annual_sharpe_ratio(
        profit_col_name="org_profit"
    )

    sum_squared_errors = 0.0
    for bet_with_trace in bets:
        estimated_p_yes = bet_with_trace.trace.answer.p_yes
        actual_answer = float(bet_with_trace.bet.market_outcome)
        sum_squared_errors += (estimated_p_yes - actual_answer) ** 2

    p_yes_mse = sum_squared_errors / len(bets)
    total_bet_amount = sum([bt.bet.amount.amount for bt in bets])
    total_bet_profit = sum([bt.bet.profit.amount for bt in bets])
    total_simulated_amount = sum([so.size for so in simulated_outcomes])
    total_simulated_profit = sum([so.profit for so in simulated_outcomes])
    roi = 100 * total_bet_profit / total_bet_amount
    simulated_roi = 100 * total_simulated_profit / total_simulated_amount

    return per_bet_details, SimulatedLifetimeDetail(
        p_yes_mse=p_yes_mse,
        total_bet_amount=total_bet_amount,
        total_bet_profit=total_bet_profit,
        total_simulated_amount=total_simulated_amount,
        total_simulated_profit=total_simulated_profit,
        roi=roi,
        simulated_roi=simulated_roi,
        sharpe_output_original=sharpe_output_original,
        sharpe_output_simulation=sharpe_output_simulation,
        maximize=total_simulated_profit,  # Metric to be maximized for.
    )


def get_objective(
    bets: list[ResolvedBetWithTrace],
    tx_block_cache: TransactionBlockCache,
) -> t.Callable[[optuna.trial.Trial], float]:
    def objective(trial: optuna.trial.Trial) -> float:
        strategy_name = trial.suggest_categorical(
            "strategy_name",
            [
                MaxAccuracyBettingStrategy.__name__,
                MaxExpectedValueBettingStrategy.__name__,
                MaxAccuracyWithKellyScaledBetsStrategy.__name__,
                KellyBettingStrategy.__name__,
            ],
        )
        bet_amount = trial.suggest_float("bet_amount", 0, 25)
        max_price_impact = (
            trial.suggest_float("max_price_impact", 0, 1.0)
            if strategy_name == KellyBettingStrategy.__name__
            else None
        )
        strategy = (
            MaxAccuracyBettingStrategy(bet_amount=bet_amount)
            if strategy_name == MaxAccuracyBettingStrategy.__name__
            else (
                MaxExpectedValueBettingStrategy(bet_amount=bet_amount)
                if strategy_name == MaxExpectedValueBettingStrategy.__name__
                else (
                    MaxAccuracyWithKellyScaledBetsStrategy(max_bet_amount=bet_amount)
                    if strategy_name == MaxAccuracyWithKellyScaledBetsStrategy.__name__
                    else (
                        KellyBettingStrategy(
                            max_bet_amount=bet_amount, max_price_impact=max_price_impact
                        )
                        if strategy_name == KellyBettingStrategy.__name__
                        else None
                    )
                )
            )
        )
        assert strategy is not None, f"Invalid {strategy_name=}"

        per_bet_details, metrics = calc_metrics(bets, strategy, tx_block_cache)

        trial.set_user_attr("per_bet_details", per_bet_details)
        trial.set_user_attr("metrics", metrics)
        trial.set_user_attr("strategy", strategy)

        return metrics.maximize

    return objective


def main() -> None:
    output_directory = Path("bet_strategy_benchmark")
    output_directory.mkdir(parents=True, exist_ok=True)

    # Get the private keys for the agents from GCP Secret Manager
    agent_gcp_secret_map = {
        # "DeployablePredictionProphetGPT4TurboFinalAgent": "pma-prophetgpt4turbo-final",
        # "DeployablePredictionProphetGPT4TurboPreviewAgent": "pma-prophetgpt4",
        # "DeployablePredictionProphetGPT4oAgent": "pma-prophetgpt3",
        # "DeployablePredictionProphetGPTo1PreviewAgent": "pma-prophet-o1-preview",
        # "DeployablePredictionProphetGPTo1MiniAgent": "pma-prophet-o1-mini",
        "DeployableOlasEmbeddingOAAgent": "pma-evo-olas-embeddingoa",
        # "DeployableThinkThoroughlyAgent": "pma-think-thoroughly",
        # "DeployableThinkThoroughlyProphetResearchAgent": "pma-think-thoroughly-prophet-research",
        # "DeployableKnownOutcomeAgent": "pma-knownoutcome",
    }

    agent_pkey_map = {
        k: get_private_key_from_gcp_secret(v) for k, v in agent_gcp_secret_map.items()
    }

    httpx_client = HttpxCachedClient().get_client()

    overall_md = ""

    print("# Agent Bet vs Simulated Bet Comparison")

    tx_block_cache = TransactionBlockCache(
        web3=OmenConditionalTokenContract().get_web3()
    )

    for agent_name, private_key in agent_pkey_map.items():
        print(f"\n## {agent_name}\n")
        api_keys = APIKeys(BET_FROM_PRIVATE_KEY=private_key)

        # Pick a time after pool token number is stored in OmenAgentMarket
        creation_start_time = utc_datetime(2024, 9, 13)  # utc_datetime(2024, 9, 13)
        creation_end_time = None  # utc_datetime(2024, 9, 23)
        # If simulating history performance, also cut by resolution time to not include markets that weren't yet resolved back then.
        resolution_end_time = creation_end_time

        langfuse = Langfuse(
            secret_key=api_keys.langfuse_secret_key.get_secret_value(),
            public_key=api_keys.langfuse_public_key,
            host=api_keys.langfuse_host,
            httpx_client=httpx_client,
        )

        traces = get_traces_for_agent(
            agent_name=agent_name,
            trace_name="process_market",
            from_timestamp=creation_start_time,
            to_timestamp=creation_end_time,
            has_output=True,
            client=langfuse,
        )
        process_market_traces: list[ProcessMarketTrace] = []
        for trace in traces:
            if process_market_trace := ProcessMarketTrace.from_langfuse_trace(trace):
                process_market_traces.append(process_market_trace)

        bets: list[ResolvedBet] = OmenAgentMarket.get_resolved_bets_made_since(
            better_address=api_keys.bet_from_address,
            start_time=creation_start_time,
            end_time=creation_end_time,
            market_resolved_before=resolution_end_time,
        )
        bets.sort(key=lambda b: b.created_time)

        # All bets should have a trace, but not all traces should have a bet
        # (e.g. if all markets are deemed unpredictable), so iterate over bets
        bets_with_traces: list[ResolvedBetWithTrace] = []
        for bet in bets:
            trace = get_trace_for_bet(bet, process_market_traces)
            if trace:
                bets_with_traces.append(ResolvedBetWithTrace(bet=bet, trace=trace))

        print(
            f"Number of bets since {creation_start_time} up to {creation_end_time=}, {resolution_end_time=}: {len(bets_with_traces)}\n"
        )

        if len(bets_with_traces) < 10:
            print("Only tiny amount of bets with traces found, skipping.")
            continue

        if len(bets_with_traces) != len(bets):
            pct_bets_without_traces = (len(bets) - len(bets_with_traces)) / len(bets)
            print(
                f"{len(bets) - len(bets_with_traces)} bets do not have a corresponding trace ({pct_bets_without_traces * 100:.2f}%), ignoring them."
            )

        tx_block_cache = TransactionBlockCache(
            web3=OmenConditionalTokenContract().get_web3()
        )

        kf = TimeSeriesSplit(n_splits=5)
        min_abs_diff: float | None = None
        best_study: optuna.Study | None = None

        for n_fold, (train_index, test_index) in enumerate(kf.split(bets_with_traces)):
            train_bets_with_traces = [bets_with_traces[i] for i in train_index]
            test_bets_with_traces = [bets_with_traces[i] for i in test_index]

            k_study = optuna.create_study(direction="maximize")
            k_study.optimize(
                get_objective(train_bets_with_traces, tx_block_cache), n_trials=200
            )
            _, testing_metrics = calc_metrics(
                test_bets_with_traces,
                k_study.best_trial.user_attrs["strategy"],
                tx_block_cache,
            )

            train_best_value = check_not_none(
                k_study.best_trial.value, "Shouldn't be None after optimizing."
            )
            test_maximize_value = testing_metrics.maximize
            abs_diff = abs(train_best_value - test_maximize_value)

            print(
                f"[{n_fold}] Best value for {agent_name} (params: {k_study.best_params}): "
                f"Training: {train_best_value} Testing: {test_maximize_value}"
            )

            if min_abs_diff is None or abs_diff < min_abs_diff:
                min_abs_diff = abs_diff
                best_study = k_study

        best_study = check_not_none(
            best_study, "Shouldn't be None after running k-folds."
        )

        print(
            f"Selected strategy with params: {best_study.best_params} (Min Abs Diff: {min_abs_diff})"
        )

        simulations_df = pd.DataFrame.from_records(
            [trial.user_attrs["metrics"] for trial in best_study.trials]
        )
        simulations_df.sort_values(by="maximize", ascending=False, inplace=True)
        overall_md += (
            f"\n\n## {agent_name}\n\n{len(bets_with_traces)} bets\n\n"
            + simulations_df.to_markdown(index=False)
        )

        with open(
            output_directory / "match_bets_with_langfuse_traces_overall.md", "w"
        ) as overall_f:
            overall_f.write(overall_md)


if __name__ == "__main__":
    main()
