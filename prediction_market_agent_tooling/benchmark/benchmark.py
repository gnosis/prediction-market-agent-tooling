import concurrent.futures
import os
import time
import typing as t
from collections import defaultdict

import numpy as np
import pandas as pd
from langchain_community.callbacks import get_openai_callback
from sklearn.metrics import precision_score, recall_score
from tqdm import tqdm

from prediction_market_agent_tooling.benchmark.agents import AbstractBenchmarkedAgent
from prediction_market_agent_tooling.benchmark.utils import (
    Market,
    MarketResolution,
    Prediction,
    PredictionsCache,
    get_llm_api_call_cost,
    should_not_happen,
)
from prediction_market_agent_tooling.tools.utils import check_not_none


class Benchmarker:
    def __init__(
        self,
        markets: t.List[Market],
        agents: t.List[AbstractBenchmarkedAgent],
        metric_fns: t.Dict[
            str, t.Callable[[list[Prediction], list[Market]], str | float | None]
        ] = {},
        cache_path: t.Optional[str] = None,
        only_cached: bool = False,
    ):
        self.registered_agents: t.List[AbstractBenchmarkedAgent] = agents
        if len(set(a.agent_name for a in self.registered_agents)) != len(
            self.registered_agents
        ):
            raise ValueError("Agents must have unique names")
        if any(m.is_cancelled for m in markets):
            raise ValueError(
                "Cancelled markets shouldn't be used in the benchmark, please filter them out."
            )

        # Predictions
        self.cache_path = cache_path
        if self.cache_path and os.path.exists(self.cache_path):
            self.predictions = PredictionsCache.load(path=self.cache_path)
        else:
            self.predictions = PredictionsCache(predictions={})

        self.only_cached = only_cached
        self.markets: list[Market] = (
            [
                m
                for m in markets
                if all(
                    self.predictions.has_market(
                        agent_name=agent.agent_name, question=m.question
                    )
                    for agent in self.registered_agents
                )
            ]
            if self.only_cached
            else markets
        )

        # Metrics
        self.metric_fns = metric_fns
        predefined_metric_fns = {
            "MSE for `p_yes`": self._compute_mse,
            "Mean confidence": self._compute_mean_confidence,
            "% within +-0.05": lambda predictions, markets: self._compute_percentage_within_range(
                predictions, markets, tolerance=0.05
            ),
            "% within +-0.1": lambda predictions, markets: self._compute_percentage_within_range(
                predictions, markets, tolerance=0.1
            ),
            "% within +-0.2": lambda predictions, markets: self._compute_percentage_within_range(
                predictions, markets, tolerance=0.2
            ),
            "% correct outcome": self._compute_correct_outcome_percentage,
            "% precision for `yes`": lambda predictions, markets: self._compute_precision_and_recall_percentages(
                predictions, markets, pos_label=1
            )[
                0
            ],
            "% precision for `no`": lambda predictions, markets: self._compute_precision_and_recall_percentages(
                predictions, markets, pos_label=0
            )[
                0
            ],
            "% recall for `yes`": lambda predictions, markets: self._compute_precision_and_recall_percentages(
                predictions, markets, pos_label=1
            )[
                1
            ],
            "% recall for `no`": lambda predictions, markets: self._compute_precision_and_recall_percentages(
                predictions, markets, pos_label=0
            )[
                1
            ],
            "confidence/p_yes error correlation": self._compute_confidence_p_yes_error_correlation,
            "Mean info_utility": self._compute_mean_info_utility,
            "Proportion answerable": self._compute_ratio_evaluated_as_answerable,
            "Proportion answered": self._compute_ratio_answered,
            "Mean cost ($)": self._compute_mean_cost,
            "Mean time (s)": self._compute_mean_time,
        }
        self.metric_fns.update(predefined_metric_fns)

    def add_prediction(
        self,
        agent: AbstractBenchmarkedAgent,
        prediction: Prediction,
        market_question: str,
    ) -> None:
        self.predictions.add_prediction(
            agent_name=agent.agent_name,
            question=market_question,
            prediction=prediction,
        )

    def get_prediction(self, agent_name: str, question: str) -> Prediction:
        return self.predictions.get_prediction(agent_name=agent_name, question=question)

    def run_agents(self, enable_timing: bool = True) -> None:
        for agent in tqdm(self.registered_agents, desc="Running agents"):
            # Filter out cached predictions
            markets_to_run = [
                m
                for m in self.markets
                if not self.predictions.has_market(
                    agent_name=agent.agent_name, question=m.question
                )
            ]

            def get_prediction_result(market: Market) -> tuple[str, Prediction]:
                with get_openai_callback() as cb:
                    start = time.time()
                    prediction = (
                        agent.check_and_predict(market_question=market.question)
                        if not market.is_resolved
                        else agent.check_and_predict_restricted(
                            market_question=market.question,
                            time_restriction_up_to=market.created_time,  # TODO: Add support for resolved_at and any time in between.
                        )
                    )

                    prediction.time = time.time() - start if enable_timing else None

                    if cb.total_tokens > 0 and cb.total_cost == 0:
                        # TODO: this is a hack to get the cost for an unsupported model
                        cb.total_cost = get_llm_api_call_cost(
                            model=agent.model,
                            prompt_tokens=cb.prompt_tokens,
                            completion_tokens=cb.completion_tokens,
                        )
                    prediction.cost = cb.total_cost
                return market.question, prediction

            # Run agents in parallel
            with concurrent.futures.ThreadPoolExecutor(
                max_workers=agent.max_workers
            ) as executor:
                futures = [
                    executor.submit(get_prediction_result, market)
                    for market in markets_to_run
                ]
                for future in tqdm(
                    concurrent.futures.as_completed(futures),
                    total=len(futures),
                    desc=f"Running {agent.agent_name}",
                ):
                    market_question, prediction = future.result()
                    self.add_prediction(
                        agent=agent,
                        prediction=prediction,
                        market_question=market_question,
                    )
                    if self.cache_path:
                        self.predictions.save(self.cache_path)

    @staticmethod
    def filter_predictions_for_answered(
        predictions: list[Prediction], markets: list[Market]
    ) -> t.Tuple[list[Prediction], list[Market]]:
        filtered_predictions, filtered_markets = [], []
        for p, m in zip(predictions, markets):
            if p.is_answered:
                filtered_predictions.append(p)
                filtered_markets.append(m)
        return filtered_predictions, filtered_markets

    def _compute_mse(
        self, predictions: t.List[Prediction], markets: t.List[Market]
    ) -> float | None:
        predictions, markets = self.filter_predictions_for_answered(
            predictions, markets
        )
        if not predictions:
            return None
        mse = sum(
            [
                (check_not_none(p.outcome_prediction).p_yes - m.p_yes) ** 2
                for p, m in zip(predictions, markets)
            ]
        ) / len(predictions)
        return mse

    def _compute_mean_confidence(
        self, predictions: t.List[Prediction], markets: t.List[Market]
    ) -> float | None:
        predictions, markets = self.filter_predictions_for_answered(
            predictions, markets
        )
        if not predictions:
            return None
        mean_confidence = sum(
            [check_not_none(p.outcome_prediction).confidence for p in predictions]
        ) / len(predictions)
        return mean_confidence

    def _compute_mean_info_utility(
        self, predictions: t.List[Prediction], markets: t.List[Market]
    ) -> float | None:
        predictions, markets = self.filter_predictions_for_answered(
            predictions, markets
        )
        predictions_with_info_utility = [
            p
            for p in predictions
            if check_not_none(p.outcome_prediction).info_utility is not None
        ]
        if not predictions_with_info_utility:
            return None
        mean_info_utility = sum(
            [
                check_not_none(check_not_none(p.outcome_prediction).info_utility)
                for p in predictions_with_info_utility
            ]
        ) / len(predictions_with_info_utility)
        return mean_info_utility

    def _compute_percentage_within_range(
        self,
        predictions: t.List[Prediction],
        markets: t.List[Market],
        tolerance: float = 0.05,
    ) -> float | None:
        predictions, markets = self.filter_predictions_for_answered(
            predictions, markets
        )
        if not predictions:
            return None

        within_range_count = 0
        for p, m in zip(predictions, markets):
            if abs(check_not_none(p.outcome_prediction).p_yes - m.p_yes) <= tolerance:
                within_range_count += 1

        return (100 * within_range_count) / len(predictions)

    def _compute_correct_outcome_percentage(
        self, predictions: t.List[Prediction], markets: t.List[Market]
    ) -> float | None:
        predictions, markets = self.filter_predictions_for_answered(
            predictions, markets
        )
        if not predictions:
            return None

        correct_outcome_count = 0
        for p, m in zip(predictions, markets):
            if (
                check_not_none(p.outcome_prediction).probable_resolution
                == m.probable_resolution
            ):
                correct_outcome_count += 1

        return (100 * correct_outcome_count) / len(predictions)

    def _compute_precision_and_recall_percentages(
        self, predictions: t.List[Prediction], markets: t.List[Market], pos_label: int
    ) -> tuple[float | None, float | None]:
        predictions, markets = self.filter_predictions_for_answered(
            predictions, markets
        )
        if not predictions:
            return None, None

        ground_truth = [
            (1 if m.probable_resolution == MarketResolution.YES else 0) for m in markets
        ]
        y_pred = [
            (
                1
                if check_not_none(p.outcome_prediction).probable_resolution
                == MarketResolution.YES
                else 0
            )
            for p in predictions
        ]

        precision = precision_score(
            ground_truth, y_pred, pos_label=pos_label, zero_division=0.0
        )
        recall = recall_score(
            ground_truth, y_pred, pos_label=pos_label, zero_division=0.0
        )

        return precision * 100, recall * 100

    def _compute_confidence_p_yes_error_correlation(
        self, predictions: t.List[Prediction], markets: t.List[Market]
    ) -> float | None:
        predictions, markets = self.filter_predictions_for_answered(
            predictions, markets
        )
        if not predictions:
            return None

        p_yes_errors = [
            abs(check_not_none(p.outcome_prediction).p_yes - m.p_yes)
            for p, m in zip(predictions, markets)
        ]
        confidences = [
            check_not_none(p.outcome_prediction).confidence for p in predictions
        ]
        return float(np.corrcoef(confidences, p_yes_errors)[0, 1])

    def _compute_mean_cost(
        self, predictions: t.List[Prediction], markets: t.List[Market]
    ) -> float | None:
        # Note: costs are optional
        costs = [p.cost for p in predictions if p.cost]
        if costs:
            return sum(costs) / len(costs)
        else:
            return None

    def _compute_mean_time(
        self, predictions: t.List[Prediction], markets: t.List[Market]
    ) -> float | None:
        # Note: times are optional
        times = [p.time for p in predictions if p.time]
        if times:
            return sum(times) / len(times)
        else:
            return None

    def _compute_ratio_evaluated_as_answerable(
        self, predictions: t.List[Prediction], markets: t.List[Market]
    ) -> float:
        return sum(1 for p in predictions if p.is_predictable) / len(predictions)

    def _compute_ratio_answered(
        self, predictions: t.List[Prediction], markets: t.List[Market]
    ) -> float:
        return sum(1 for p in predictions if p.is_answered) / len(predictions)

    def compute_metrics(self) -> t.Dict[str, t.List[t.Any]]:
        metrics: dict[str, list[str | float | None]] = {}
        metrics["Agents"] = [a.agent_name for a in self.registered_agents]

        for name, fn in self.metric_fns.items():
            metrics[name] = []
            for agent in self.registered_agents:
                ordered_predictions = [
                    self.get_prediction(
                        question=market.question, agent_name=agent.agent_name
                    )
                    for market in self.markets
                ]
                metrics[name].append(fn(ordered_predictions, self.markets))

        return metrics

    def get_markets_summary(self) -> t.Dict[str, t.List[str | float]]:
        market_questions = [q.question for q in self.markets]
        urls = [q.url for q in self.markets]
        markets_summary: dict[str, list[str | float]] = {
            "Market Question": [
                f"[{question}]({url})" for question, url in zip(market_questions, urls)
            ],
        }

        for agent in [a.agent_name for a in self.registered_agents]:
            agent_predictions = [
                self.get_prediction(agent_name=agent, question=q)
                for q in market_questions
            ]
            markets_summary[f"{agent} p_yes"] = [
                (
                    f"{p.outcome_prediction.p_yes:.2f} [{p.outcome_prediction.probable_resolution.value}]"
                    if p.is_predictable
                    and p.outcome_prediction  # Is answerable and answered
                    else (
                        "S"
                        if not p.is_predictable  # Skipped (evaluated to be not predictable)
                        else (
                            "F"
                            if p.is_predictable
                            and not p.outcome_prediction  # Failed (no prediction)
                            else should_not_happen(
                                f"Unexpected case in get_markets_summary() for {p}."
                            )
                        )
                    )
                )
                for p in agent_predictions
            ]
        markets_summary[f"reference p_yes"] = [
            f"{m.p_yes:.2f} [{m.probable_resolution}]" for m in self.markets
        ]
        return markets_summary

    def get_markets_results(self) -> dict[str, list[str | float]]:
        return {
            "Number of markets": [len(self.markets)],
            "Proportion resolved": [
                sum(1 for m in self.markets if m.is_resolved) / len(self.markets)
            ],
            "Proportion YES": [
                sum(
                    1
                    for m in self.markets
                    if m.probable_resolution == MarketResolution.YES
                )
                / len(self.markets)
            ],
            "Proportion NO": [
                sum(
                    1
                    for m in self.markets
                    if m.probable_resolution == MarketResolution.NO
                )
                / len(self.markets)
            ],
        }

    def calculate_expected_returns(
        self, prediction: Prediction, market: Market
    ) -> float | None:
        """
        The expected value if betting on a binary market in its initialized state of 50:50 'yes' and 'no' shares, with the assumption that the correct `p_yes` is that of the market.
        """
        if not prediction.is_answered:
            return None

        # TODO: Add support for different bet sizes -- if we bet a low amount (such as <10 units), the real shares will be very close to that we calculate below (bet_units / share_price),
        # but if one bets a lot, it will change the share price along the way, and so he/she receives less than `bet_units / share_price`, but it's more complicated to calculate.
        bet_units = 10  # Assuming the agent always bet 10 units per market.

        assert prediction.outcome_prediction is not None
        # Assume that market starts at 50/50 and so the price is 0.5 at the time we are buying it,
        # we can't use {yes,no}_outcome_price atm, because it would just cancel out to EV = 0.0,
        # as it's the same as the probability.
        yes_shares = (
            bet_units / 0.5  # market.yes_outcome_price
            if prediction.outcome_prediction.probable_resolution == MarketResolution.YES
            and market.yes_outcome_price > 0
            else 0
        )
        no_shares = (
            bet_units / 0.5  # market.no_outcome_price
            if prediction.outcome_prediction.probable_resolution == MarketResolution.NO
            and market.no_outcome_price > 0
            else 0
        )

        # If we don't bet, we don't have any expected returns.
        if yes_shares == 0 and no_shares == 0:
            return None

        expected_value = (
            yes_shares * market.p_yes + no_shares * (1 - market.p_yes) - bet_units
        )
        expected_returns_perc = 100 * expected_value / bet_units

        return expected_returns_perc

    def compute_expected_returns_summary(
        self,
    ) -> t.Tuple[dict[str, list[str | float]], dict[str, list[str | float | None]]]:
        overall_summary: dict[str, list[str | float]] = defaultdict(list)

        for agent in self.registered_agents:
            expected_returns = []

            for market in self.markets:
                if (
                    prediction := self.get_prediction(agent.agent_name, market.question)
                ).is_answered and (
                    expected_return := self.calculate_expected_returns(
                        prediction, market
                    )
                ) is not None:
                    expected_returns.append(expected_return)

            overall_summary["Agent"].append(agent.agent_name)
            overall_summary["Mean expected returns"].append(
                float(np.mean(expected_returns))
            )
            overall_summary["Median expected returns"].append(
                float(np.median(expected_returns))
            )
            overall_summary["Total expected returns"].append(
                float(np.sum(expected_returns))
            )

        per_market: dict[str, list[str | float | None]] = defaultdict(list)

        for market in self.markets:
            per_market["Market Question"].append(market.question)

            for agent in self.registered_agents:
                per_market[agent.agent_name].append(
                    self.calculate_expected_returns(
                        self.get_prediction(agent.agent_name, market.question), market
                    )
                )

        return dict(overall_summary), dict(per_market)

    def generate_markdown_report(self) -> str:
        md = "# Comparison Report\n\n"
        md += "## Market Results\n\n"
        md += pd.DataFrame(self.get_markets_results()).to_markdown(index=False)
        md += "\n\n"
        md += "## Agent Results\n\n"
        md += "### Summary Statistics\n\n"
        md += pd.DataFrame(self.compute_metrics()).to_markdown(index=False)
        md += "\n\n"
        md += "### Markets\n\n"
        md += pd.DataFrame(self.get_markets_summary()).to_markdown(index=False)
        md += "\n\n"
        md += "### Expected value\n\n"
        overall_summary, per_market = self.compute_expected_returns_summary()
        md += pd.DataFrame(overall_summary).to_markdown(index=False)
        md += "\n\n"
        md += pd.DataFrame(per_market).to_markdown(index=False)
        return md
