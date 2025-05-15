import typing as t
from datetime import timedelta
from pathlib import Path

import optuna
import pandas as pd
import tenacity
from eth_typing import HexAddress, HexStr
from langfuse import Langfuse
from pydantic import BaseModel
from web3.exceptions import TransactionNotFound

from prediction_market_agent_tooling.config import APIKeys
from prediction_market_agent_tooling.deploy.agent import AnsweredEnum, MarketType
from prediction_market_agent_tooling.deploy.betting_strategy import (
    BettingStrategy,
    CategoricalProbabilisticAnswer,
    GuaranteedLossError,
    KellyBettingStrategy,
    MaxAccuracyWithKellyScaledBetsStrategy,
    MaxExpectedValueBettingStrategy,
    MultiCategoricalMaxAccuracyBettingStrategy,
    TradeType,
)
from prediction_market_agent_tooling.gtypes import (
    USD,
    CollateralToken,
    OutcomeStr,
    private_key_type,
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
    get_omen_market_by_market_id_cached,
)
from prediction_market_agent_tooling.tools.datetime_utc import DatetimeUTC
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
from prediction_market_agent_tooling.tools.utils import utc_datetime, utcnow

if t.TYPE_CHECKING:
    from optuna.trial import FrozenTrial

optuna.logging.set_verbosity(optuna.logging.WARNING)


class SimulatedOutcome(BaseModel):
    size: CollateralToken
    direction: OutcomeStr
    correct: bool
    profit: CollateralToken


def get_outcome_for_trace(
    strategy: BettingStrategy,
    trace: ProcessMarketTrace,
    market_outcome: OutcomeStr,
    actual_placed_bet: ResolvedBet,
    tx_block_cache: TransactionBlockCache,
) -> SimulatedOutcome | None:
    market = trace.market
    answer = trace.answer

    try:
        trades = strategy.calculate_trades(
            existing_position=None,
            answer=CategoricalProbabilisticAnswer(
                probabilities=answer.probabilities,
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
    # We use a historical state (by passing in a block_number as arg) to get the correct outcome token balances.
    try:
        bet_tx_block_number = tx_block_cache.get_block_number(actual_placed_bet.id)
    except tenacity.RetryError as e:
        if isinstance(e.last_attempt.exception(), TransactionNotFound):
            return None
        raise
    # We need market at state before the bet was placed, otherwise it wouldn't be fair (outcome price is higher from the original bet at `bet_tx_block_number`)
    market_before_placing_bet = get_omen_market_by_market_id_cached(
        HexAddress(HexStr(market.id)), block_number=bet_tx_block_number - 1
    )
    omen_agent_market_before_placing_bet = OmenAgentMarket.from_data_model(
        market_before_placing_bet
    )

    buy_trade_in_tokes = omen_agent_market_before_placing_bet.get_in_token(
        buy_trade.amount
    )
    if not correct:
        profit = -buy_trade_in_tokes
    else:
        received_outcome_tokens = (
            omen_agent_market_before_placing_bet.get_buy_token_amount(
                buy_trade.amount, outcome=buy_trade.outcome
            )
        )
        profit = received_outcome_tokens.as_token - buy_trade_in_tokes

    return SimulatedOutcome(
        size=buy_trade_in_tokes,
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
        if simulated_outcome is None:
            continue
        simulated_outcomes.append(simulated_outcome)

        simulation_detail = SimulatedBetDetail(
            strategy=repr(strategy),
            url=bet_with_trace.trace.market.url,
            probabilities=bet_with_trace.trace.market.probabilities,
            agent_prob_multi=bet_with_trace.trace.answer.probabilities,
            agent_conf=round(bet_with_trace.trace.answer.confidence, 4),
            org_bet=round(bet_with_trace.bet.amount, 4),
            sim_bet=round(simulated_outcome.size, 4),
            org_dir=bet_with_trace.bet.outcome,
            sim_dir=simulated_outcome.direction,
            org_profit=round(bet_with_trace.bet.profit, 4),
            sim_profit=round(simulated_outcome.profit, 4),
            timestamp=bet_with_trace.trace.timestamp_datetime,
        )
        per_bet_details.append(simulation_detail)

    sum_squared_errors = 0.0
    for bet_with_trace in bets:
        predicted_probs = bet_with_trace.trace.answer.probabilities

        # Create actual outcome vector (1 for winning outcome, 0 for others)
        actual_outcome = bet_with_trace.bet.market_outcome
        sum_squared_errors_outcome = 0.0
        for outcome, predicted_prob in predicted_probs.items():
            actual_value = 1.0 if outcome == actual_outcome else 0.0
            sum_squared_errors_outcome += (predicted_prob - actual_value) ** 2
        sum_squared_errors += sum_squared_errors_outcome / len(predicted_probs)

    p_yes_mse = sum_squared_errors / len(bets)
    total_bet_amount = sum([bt.bet.amount for bt in bets], start=CollateralToken(0))
    total_bet_profit = sum([bt.bet.profit for bt in bets], start=CollateralToken(0))
    total_simulated_amount = sum(
        [so.size for so in simulated_outcomes], start=CollateralToken(0)
    )
    total_simulated_profit = sum(
        [so.profit for so in simulated_outcomes], start=CollateralToken(0)
    )
    roi = 100 * total_bet_profit.value / total_bet_amount.value
    simulated_roi = 100 * (total_simulated_profit / total_simulated_amount)

    return per_bet_details, SimulatedLifetimeDetail(
        p_yes_mse=p_yes_mse,
        total_bet_amount=total_bet_amount,
        total_bet_profit=total_bet_profit,
        total_simulated_amount=total_simulated_amount,
        total_simulated_profit=total_simulated_profit,
        roi=roi,
        simulated_roi=simulated_roi,
        maximize=total_simulated_profit.value,  # Metric to be maximized for.
    )


def group_datetime(dt: DatetimeUTC) -> tuple[int, int]:
    week_number = dt.isocalendar().week
    return dt.year, week_number


def get_objective(
    bets: list[list[ResolvedBetWithTrace]],
    upper_bet_amount: float,
    upper_max_price_impact: float,
    tx_block_cache: TransactionBlockCache,
) -> t.Callable[[optuna.trial.Trial], list[float]]:
    def objective(trial: optuna.trial.Trial) -> list[float]:
        strategy_name = trial.suggest_categorical(
            "strategy_name",
            [
                MultiCategoricalMaxAccuracyBettingStrategy.__name__,
                MaxAccuracyWithKellyScaledBetsStrategy.__name__,
                KellyBettingStrategy.__name__,
            ],
        )
        bet_amount = USD(trial.suggest_float("bet_amount", 0, upper_bet_amount))
        max_price_impact = (
            trial.suggest_float("max_price_impact", 0, upper_max_price_impact)
            if strategy_name == KellyBettingStrategy.__name__
            else None
        )

        strategy_constructors: dict[str, t.Callable[[], BettingStrategy]] = {
            MultiCategoricalMaxAccuracyBettingStrategy.__name__: lambda: MultiCategoricalMaxAccuracyBettingStrategy(
                bet_amount=bet_amount
            ),
            MaxAccuracyWithKellyScaledBetsStrategy.__name__: lambda: MaxAccuracyWithKellyScaledBetsStrategy(
                max_bet_amount=bet_amount
            ),
            MaxExpectedValueBettingStrategy.__name__: lambda: MaxExpectedValueBettingStrategy(
                bet_amount=bet_amount
            ),
            KellyBettingStrategy.__name__: lambda: KellyBettingStrategy(
                max_bet_amount=bet_amount, max_price_impact=max_price_impact
            ),
        }

        strategy_constructor = strategy_constructors.get(strategy_name)
        if strategy_constructor is None:
            raise ValueError(f"Invalid strategy name: {strategy_name}")
        strategy = strategy_constructor()

        per_bet_details, metrics = list(
            zip(*[calc_metrics(bs, strategy, tx_block_cache) for bs in bets])
        )

        trial.set_user_attr("per_bet_details", per_bet_details[-1])
        trial.set_user_attr("metrics_dict", metrics[-1].model_dump())
        trial.set_user_attr("strategy", strategy)

        if bets[0][0].bet.created_time > bets[-1][0].bet.created_time:
            raise RuntimeError(
                "Groups of bets should be sorted ascending by created time."
            )

        # During optimization, put more weight into recent weeks.
        n = len(metrics)
        weights = (
            [0.5 + i * (1.0 - 0.5) / (n - 1) for i in range(n)] if n > 1 else [1.0]
        )
        return [w * m.maximize for w, m in zip(weights, metrics)]

    return objective


def generate_folds(
    bets_with_traces: list[ResolvedBetWithTrace],
) -> list[tuple[list[ResolvedBetWithTrace], list[ResolvedBetWithTrace]]]:
    """
    Custom implementation similar to scikit's TimeSeriesSplit, but allows to create k-groups based on arbitrary function.
    """
    groups = sorted(
        set(
            group_datetime(bets_with_trace.bet.created_time)
            for bets_with_trace in bets_with_traces
        )
    )
    folds = []

    for train_group, test_group in zip(groups, groups[1:]):
        train_bets_with_traces = [
            bets_with_trace
            for bets_with_trace in bets_with_traces
            if group_datetime(bets_with_trace.bet.created_time) == train_group
        ]
        test_bets_with_traces = [
            bets_with_trace
            for bets_with_trace in bets_with_traces
            if group_datetime(bets_with_trace.bet.created_time) == test_group
        ]

        # Skip training fold if it has less than 3 days of data, otherwise, Sharpe calculation returns NaNs.
        n_of_unique_days = len(
            set(
                bets_with_trace.bet.created_time.date()
                for bets_with_trace in train_bets_with_traces
            )
        )
        if n_of_unique_days < 3:
            continue

        folds.append((train_bets_with_traces, test_bets_with_traces))

    if not folds:
        raise RuntimeError(f"No data was split into folds groups!")

    return folds


def choose_best_trial(study: optuna.Study) -> "FrozenTrial":
    # Just returns the first one as sorted by default by Optuna, but keep as separate function in case we want to experiment with this.
    return study.best_trials[0]


def run_optuna_study(
    train_bets_with_traces: list[list[ResolvedBetWithTrace]],
    test_bets_with_traces: list[ResolvedBetWithTrace],
    upper_bet_amount: float,
    upper_max_price_impact: float,
    tx_block_cache: TransactionBlockCache,
) -> tuple[optuna.Study, SimulatedLifetimeDetail]:
    study = optuna.create_study(directions=["maximize" for _ in train_bets_with_traces])
    study.optimize(
        get_objective(
            bets=train_bets_with_traces,
            upper_bet_amount=upper_bet_amount,
            upper_max_price_impact=upper_max_price_impact,
            tx_block_cache=tx_block_cache,
        ),
        # Multiply by number of groups, because with each fold, the optimization gets harder due to the additional metric.
        n_trials=500 * len(train_bets_with_traces),
        n_jobs=-1,
    )
    _, testing_metrics = calc_metrics(
        test_bets_with_traces,
        choose_best_trial(study).user_attrs["strategy"],
        tx_block_cache,
    )
    return study, testing_metrics


def main() -> None:
    output_directory = Path("bet_strategy_benchmark")
    output_directory.mkdir(parents=True, exist_ok=True)

    # Get the private keys for the agents from GCP Secret Manager
    agent_gcp_secret_map = {
        "DeployablePredictionProphetGPT4TurboFinalAgent": "pma-prophetgpt4turbo-final",
        "DeployablePredictionProphetGPT4TurboPreviewAgent": "pma-prophetgpt4",
        "DeployablePredictionProphetGPT4oAgent": "pma-prophetgpt3",
        "DeployablePredictionProphetGPTo1PreviewAgent": "pma-prophet-o1-preview",
        "DeployablePredictionProphetGPTo1MiniAgent": "pma-prophet-o1-mini",
        "DeployableOlasEmbeddingOAAgent": "pma-evo-olas-embeddingoa",
        "DeployableThinkThoroughlyAgent": "pma-think-thoroughly",
        "DeployableThinkThoroughlyProphetResearchAgent": "pma-think-thoroughly-prophet-research",
        "DeployableKnownOutcomeAgent": "pma-knownoutcome",
        "DeployablePredictionProphetGemini20Flash": "prophet-gemini20flash",
        "DeployablePredictionProphetDeepSeekR1": "prophet-deepseekr1",
        "DeployablePredictionProphetDeepSeekChat": "prophet-deepseekchat",
        "DeployablePredictionProphetGPT4ominiAgent": "pma-prophet-gpt4o-mini",
        "DeployablePredictionProphetGPTo1": "pma-prophet-o1",
        "DeployablePredictionProphetGPTo3mini": "pma-prophet-o3-mini",
        "DeployablePredictionProphetClaude3OpusAgent": "prophet-claude3-opus",
        "DeployablePredictionProphetClaude35HaikuAgent": "prophet-claude35-haiku",
        "DeployablePredictionProphetClaude35SonnetAgent": "prophet-claude35-sonnet",
        "AdvancedAgent": "advanced-agent",
    }

    httpx_client = HttpxCachedClient().get_client()

    overall_md = ""

    print("# Agent Bet vs Simulated Bet Comparison")

    tx_block_cache = TransactionBlockCache(
        web3=OmenConditionalTokenContract().get_web3()
    )

    for agent_name, private_key in agent_gcp_secret_map.items():
        print(f"\n## {agent_name}\n")
        # Get the private key for the agent from GCP Secret Manager,
        # but we don't have an standardized format, so try until it success.
        try:
            api_keys = APIKeys(
                BET_FROM_PRIVATE_KEY=private_key_type(
                    f"gcps:{private_key}:private_key"
                ),
                SAFE_ADDRESS=f"gcps:{private_key}:safe_address",
            )
        except Exception:
            try:
                api_keys = APIKeys(
                    BET_FROM_PRIVATE_KEY=private_key_type(
                        f"gcps:{private_key}:private_key"
                    ),
                    SAFE_ADDRESS=f"gcps:{private_key}:SAFE_ADDRESS",
                )
            except Exception:
                try:
                    api_keys = APIKeys(
                        BET_FROM_PRIVATE_KEY=private_key_type(
                            f"gcps:{private_key}:private_key"
                        ),
                        SAFE_ADDRESS=None,
                    )
                except Exception as e:
                    raise ValueError("No usual combination of keys found.") from e

        creation_start_time = max(
            # Two reasons for this date:
            # 1. Time after pool token number is stored in OmenAgentMarket
            # 2. The day when we used customized betting strategies: https://github.com/gnosis/prediction-market-agent/pull/494
            utc_datetime(2024, 10, 5),
            # However, Langfuse doesn't allow to filter only for traces for a specific agent, so limit only to last N months of data to speed up the process.
            utcnow() - timedelta(days=60),
        )

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
            has_output=True,
            client=langfuse,
            tags=[AnsweredEnum.ANSWERED.value, MarketType.OMEN.value],
        )
        process_market_traces: list[ProcessMarketTrace] = []
        for trace in traces:
            if process_market_trace := ProcessMarketTrace.from_langfuse_trace(trace):
                process_market_traces.append(process_market_trace)

        bets: list[ResolvedBet] = OmenAgentMarket.get_resolved_bets_made_since(
            better_address=api_keys.bet_from_address,
            start_time=creation_start_time,
            end_time=None,
        )
        bets.sort(key=lambda b: b.created_time)

        # All bets should have a trace, but not all traces should have a bet
        # (e.g. if all markets are deemed unpredictable), so iterate over bets
        bets_with_traces: list[ResolvedBetWithTrace] = []
        for bet in bets:
            trace = get_trace_for_bet(bet, process_market_traces)
            if trace:
                bets_with_traces.append(ResolvedBetWithTrace(bet=bet, trace=trace))

        print(f"Number of bets since {creation_start_time}: {len(bets_with_traces)}\n")

        if len(bets_with_traces) < 10:
            print("Only tiny amount of bets with traces found, skipping.")
            continue

        if len(bets_with_traces) != len(bets):
            pct_bets_without_traces = (len(bets) - len(bets_with_traces)) / len(bets)
            print(
                f"{len(bets) - len(bets_with_traces)} bets do not have a corresponding trace ({pct_bets_without_traces * 100:.2f}%), ignoring them.\n"
            )

        tx_block_cache = TransactionBlockCache(
            web3=OmenConditionalTokenContract().get_web3()
        )

        upper_bet_amount = 25
        upper_max_price_impact = 1.0
        folds = generate_folds(bets_with_traces)

        total_simulation_profit, total_original_profit = CollateralToken(
            0
        ), CollateralToken(0)

        for fold_idx, (_, test_bets_with_traces) in enumerate(folds):
            used_training_folds = [train for train, _ in folds[: fold_idx + 1]]
            k_study_on_train, testing_metrics = run_optuna_study(
                used_training_folds,
                test_bets_with_traces,
                upper_bet_amount,
                upper_max_price_impact,
                tx_block_cache,
            )
            k_study_best_trial = choose_best_trial(k_study_on_train)
            last_study = k_study_on_train

            print(
                f"[{fold_idx+1} / {len(folds)}] Best value for {agent_name} (params: {k_study_best_trial.params}, n train bets: {sum(1 for fold in used_training_folds for _ in fold)}, n test bets: {len(test_bets_with_traces)}): "
                f"Training maximization: {k_study_best_trial.values} "
                f"Testing profit: {testing_metrics.total_simulated_profit:.2f} "
                f"Original profit on Testing: {testing_metrics.total_bet_profit:.2f} "
                f"(testing dates {test_bets_with_traces[0].bet.created_time.date()} to {test_bets_with_traces[-1].bet.created_time.date()})"
            )

            total_simulation_profit += testing_metrics.total_simulated_profit
            total_original_profit += testing_metrics.total_bet_profit

            # After the initial parameters are found, allow only small upgrades.
            # As there is no good reason for the agent to be suddenly better by a huge margin.
            # TODO: If we would run this script in an automated way, then I think this should be uncommented.
            # upper_bet_amount = (
            #     k_study_best_trial.params["bet_amount"] * 1.5
            # )
            # upper_max_price_impact = (
            #     k_study_best_trial.params["max_price_impact"] * 1.5
            #     if "max_price_impact" in k_study_best_trial.params
            #     else upper_max_price_impact
            # )

            # If we were in loss on testing set, check out if it's even possible to be profitable on it.
            # If the result is negative or very small, there was no chance of being in profit.
            if testing_metrics.maximize < 0:
                k_study_on_test = run_optuna_study(
                    [
                        test_bets_with_traces  # Not a bug, we really want to test out study on test data itself here.
                    ],
                    test_bets_with_traces,
                    upper_bet_amount,
                    upper_max_price_impact,
                    tx_block_cache,
                )[0]
                print(
                    f"  !!! Best value on this testing set: {k_study_on_test.best_trial.value:.2f}"
                )

        print()
        print(f"Total simulated profit: {total_simulation_profit}")
        print(f"Total original profit: {total_original_profit}")
        print()

        simulations_df = pd.DataFrame.from_records(
            [trial.user_attrs["metrics_dict"] for trial in last_study.trials]
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
