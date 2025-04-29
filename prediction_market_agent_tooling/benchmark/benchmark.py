import concurrent.futures
import os
import typing as t
from collections import defaultdict

import numpy as np
import pandas as pd
from sklearn.metrics import precision_score, recall_score
from tqdm import tqdm

from prediction_market_agent_tooling.benchmark.agents import AbstractBenchmarkedAgent
from prediction_market_agent_tooling.benchmark.utils import Prediction, PredictionsCache
from prediction_market_agent_tooling.gtypes import OutcomeStr
from prediction_market_agent_tooling.markets.agent_market import AgentMarket
from prediction_market_agent_tooling.tools.costs import openai_costs
from prediction_market_agent_tooling.tools.utils import (
    check_not_none,
    should_not_happen,
)


class Benchmarker:
    def __init__(
        self,
        markets: t.Sequence[AgentMarket],
        agents: t.List[AbstractBenchmarkedAgent],
        metric_fns: t.Dict[
            str,
            t.Callable[[list[Prediction], t.Sequence[AgentMarket]], str | float | None],
        ] = {},
        cache_path: t.Optional[str] = None,
        only_cached: bool = False,
    ):
        self.registered_agents: t.List[AbstractBenchmarkedAgent] = agents
        if len(set(a.agent_name for a in self.registered_agents)) != len(
            self.registered_agents
        ):
            raise ValueError("Agents must have unique names")
        if any(m.has_unsuccessful_resolution() for m in markets):
            raise ValueError(
                "Unsuccessful markets shouldn't be used in the benchmark, please filter them out."
            )

        # Predictions
        self.cache_path = cache_path
        if self.cache_path and os.path.exists(self.cache_path):
            self.predictions = PredictionsCache.load(path=self.cache_path)
        else:
            self.predictions = PredictionsCache(predictions={})

        self.only_cached = only_cached
        self.markets: t.Sequence[AgentMarket] = (
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
                predictions, markets, average_error_tolerance=0.05
            ),
            "% within +-0.1": lambda predictions, markets: self._compute_percentage_within_range(
                predictions, markets, average_error_tolerance=0.1
            ),
            "% within +-0.2": lambda predictions, markets: self._compute_percentage_within_range(
                predictions, markets, average_error_tolerance=0.2
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
        for agent in self.registered_agents:
            # Filter out cached predictions
            markets_to_run = [
                m
                for m in self.markets
                if not self.predictions.has_market(
                    agent_name=agent.agent_name, question=m.question
                )
            ]

            def get_prediction_result(
                market: AgentMarket,
            ) -> tuple[str, Prediction]:
                with openai_costs(model=agent.model) as costs:
                    prediction = (
                        agent.check_and_predict(market_question=market.question)
                        if not market.is_resolved()
                        else (
                            agent.check_and_predict_restricted(
                                market_question=market.question,
                                time_restriction_up_to=market.created_time,  # TODO: Add support for resolved_at and any time in between.
                            )
                            if market.created_time is not None
                            else should_not_happen()
                        )
                    )
                    prediction.time = costs.time
                    prediction.cost = costs.cost
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
        predictions: list[Prediction], markets: t.Sequence[AgentMarket]
    ) -> t.Tuple[list[Prediction], list[AgentMarket]]:
        filtered_predictions, filtered_markets = [], []
        for p, m in zip(predictions, markets):
            if p.is_answered:
                filtered_predictions.append(p)
                filtered_markets.append(m)
        return filtered_predictions, filtered_markets

    def _compute_mse(
        self, predictions: t.List[Prediction], markets: t.Sequence[AgentMarket]
    ) -> float | None:
        predictions, markets = self.filter_predictions_for_answered(
            predictions, markets
        )
        if not predictions:
            return None

        total_squared_errors = 0.0
        for prediction, market in zip(predictions, markets):
            squared_errors = self.calculate_squared_errors(prediction, market)
            total_squared_errors += squared_errors

        return total_squared_errors

    @staticmethod
    def calculate_errors_between_prediction_and_market(
        prediction: Prediction, market: AgentMarket
    ) -> list[float]:
        pred_probs = check_not_none(prediction.outcome_prediction).probabilities_multi
        market_probs = market.probability_map

        # Get common outcomes between prediction and market
        common_outcomes = set(pred_probs.keys()) & set(market_probs.keys())

        errors = [
            (pred_probs[outcome] - market_probs[outcome]) for outcome in common_outcomes
        ]

        return errors

    @staticmethod
    def calculate_squared_errors(prediction: Prediction, market: AgentMarket) -> float:
        errors = Benchmarker.calculate_errors_between_prediction_and_market(
            prediction, market
        )
        squared_errors = sum([err**2 for err in errors], 0.0)
        return squared_errors

    def _compute_mean_confidence(
        self, predictions: t.List[Prediction], markets: t.Sequence[AgentMarket]
    ) -> float | None:
        predictions, _ = self.filter_predictions_for_answered(predictions, markets)
        if not predictions:
            return None
        mean_confidence = sum(
            [check_not_none(p.outcome_prediction).confidence for p in predictions]
        ) / len(predictions)
        return mean_confidence

    def _compute_mean_info_utility(
        self, predictions: t.List[Prediction], markets: t.Sequence[AgentMarket]
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
        markets: t.Sequence[AgentMarket],
        average_error_tolerance: float = 0.05,
    ) -> float | None:
        predictions, markets = self.filter_predictions_for_answered(
            predictions, markets
        )
        if not predictions:
            return None

        predictions_within_range = 0.0
        for prediction, market in zip(predictions, markets):
            squared_errors = self.calculate_squared_errors(prediction, market)
            if squared_errors <= (average_error_tolerance**2):
                predictions_within_range += 1

        return (100 * predictions_within_range) / len(predictions)

    def _compute_correct_outcome_percentage(
        self, predictions: t.List[Prediction], markets: t.Sequence[AgentMarket]
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
        self,
        predictions: t.List[Prediction],
        markets: t.Sequence[AgentMarket],
        pos_label: int,
    ) -> tuple[float | None, float | None]:
        predictions, markets = self.filter_predictions_for_answered(
            predictions, markets
        )
        if not predictions:
            return None, None

        ground_truth = [
            m.probable_resolution.outcome if m.probable_resolution else None
            for m in markets
        ]
        y_pred = [
            p.outcome_prediction.probable_resolution.outcome
            if p.outcome_prediction is not None
            else None
            for p in predictions
        ]

        # Filter out None values
        valid_indices = [
            i
            for i, (gt, pred) in enumerate(zip(ground_truth, y_pred))
            if gt is not None and pred is not None
        ]
        if not valid_indices:
            return None, None

        ground_truth = [ground_truth[i] for i in valid_indices]
        y_pred = [y_pred[i] for i in valid_indices]
        precision = precision_score(
            ground_truth, y_pred, average="micro", zero_division=0.0
        )
        recall = recall_score(ground_truth, y_pred, average="micro", zero_division=0.0)
        return precision * 100, recall * 100

    def _compute_confidence_p_yes_error_correlation(
        self, predictions: t.List[Prediction], markets: t.Sequence[AgentMarket]
    ) -> float | None:
        predictions, markets = self.filter_predictions_for_answered(
            predictions, markets
        )
        if not predictions:
            return None

        p_yes_errors = []
        for p, m in zip(predictions, markets):
            errors = self.calculate_errors_between_prediction_and_market(p, m)
            mean_error = sum([abs(i) for i in errors]) / len(errors)
            p_yes_errors.append(mean_error)

        confidences = [
            check_not_none(p.outcome_prediction).confidence for p in predictions
        ]
        return float(np.corrcoef(confidences, p_yes_errors)[0, 1])

    def _compute_mean_cost(
        self, predictions: t.List[Prediction], markets: t.Sequence[AgentMarket]
    ) -> float | None:
        # Note: costs are optional
        costs = [p.cost for p in predictions if p.cost]
        if costs:
            return sum(costs) / len(costs)
        else:
            return None

    def _compute_mean_time(
        self, predictions: t.List[Prediction], markets: t.Sequence[AgentMarket]
    ) -> float | None:
        # Note: times are optional
        times = [p.time for p in predictions if p.time]
        if times:
            return sum(times) / len(times)
        else:
            return None

    def _compute_ratio_evaluated_as_answerable(
        self, predictions: t.List[Prediction], markets: t.Sequence[AgentMarket]
    ) -> float:
        return sum(1 for p in predictions if p.is_predictable) / len(predictions)

    def _compute_ratio_answered(
        self, predictions: t.List[Prediction], markets: t.Sequence[AgentMarket]
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
                    f"{p.outcome_prediction.probabilities_multi} [{p.outcome_prediction.probable_resolution}]"
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
        markets_summary[f"reference probability_map"] = [
            f"{m.probability_map} [{m.probable_resolution}]" for m in self.markets
        ]
        return markets_summary

    def get_markets_results(self) -> dict[str, list[str | float]]:
        outcome_counts: dict[OutcomeStr, int] = defaultdict(int)
        total_markets = len(self.markets)

        for market in self.markets:
            resolution = market.probable_resolution
            if resolution.outcome:
                outcome_counts[resolution.outcome] += 1

        proportions = {
            outcome: count / total_markets for outcome, count in outcome_counts.items()
        }
        return {
            "Number of markets": [total_markets],
            "Proportion resolved": [
                sum(1 for m in self.markets if m.is_resolved()) / total_markets
            ],
            **{
                f"Proportion {outcome}": [proportions.get(outcome, 0)]
                for outcome in outcome_counts
            },
        }

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
        return md
