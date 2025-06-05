import json
import time
from functools import partial
from typing import Any, Dict

import pandas as pd
from prediction_prophet.autonolas.research import Prediction as PredictionProphet
from prediction_prophet.functions.research import Research
from pydantic import BaseModel
from pydantic_ai import Agent
from sklearn.metrics import (
    accuracy_score,
    classification_report,
    confusion_matrix,
    f1_score,
    precision_score,
    recall_score,
)

from prediction_market_agent_tooling.benchmark.utils import Prediction
from prediction_market_agent_tooling.deploy.betting_strategy import BettingStrategy
from prediction_market_agent_tooling.gtypes import Probability
from prediction_market_agent_tooling.loggers import logger
from prediction_market_agent_tooling.markets.agent_market import AgentMarket
from prediction_market_agent_tooling.markets.data_models import (
    CategoricalProbabilisticAnswer,
    ProbabilisticAnswer,
    Trade,
)
from prediction_market_agent_tooling.markets.omen.omen import OmenAgentMarket


class ProphetTestResult(BaseModel):
    run_name: str
    market_question: str
    research: Research
    prediction: Prediction
    trades: list[Trade]
    simulated_outcome: bool
    market_result: bool


class ProphetAgentTester:
    def __init__(
        self,
        prophet_research: partial[Research],
        prophet_predict: partial[PredictionProphet],
        betting_strategy: BettingStrategy,
        include_research: bool = False,
        include_prediction: bool = False,
        mocked_agent_name: str = "DeployablePredictionProphetGPT4oAgent",
        max_trades_to_test_on: int = 10,
        run_name: str = "test_prophet_agent_baseline",
        delay_between_trades: float = 0.5,
    ):
        self.prophet_research = prophet_research
        self.prophet_predict = prophet_predict
        self.betting_strategy = betting_strategy
        self.max_trades_to_test_on = max_trades_to_test_on
        self.mocked_agent_name = mocked_agent_name
        self.include_research = include_research
        self.include_prediction = include_prediction
        self.run_name = run_name
        self.delay_between_trades = delay_between_trades

    def test_prophet_agent(
        self, dataset: pd.DataFrame, research_agent: Agent, prediction_agent: Agent
    ) -> list[ProphetTestResult]:
        filtered_dataset = dataset[dataset["agent_name"] == self.mocked_agent_name]
        available_trades = len(filtered_dataset)
        trades_to_process = min(self.max_trades_to_test_on, available_trades)

        logger.info(
            f"Found {available_trades} trades for {self.mocked_agent_name}, processing {trades_to_process}"
        )

        results = []

        for index, (row_index, item) in enumerate(
            filtered_dataset.head(self.max_trades_to_test_on).iterrows()
        ):
            logger.info(
                f"Processing trade {index + 1}/{trades_to_process}: {item['market_question']}"
            )

            if self.delay_between_trades > 0:
                time.sleep(self.delay_between_trades)

            market = OmenAgentMarket.model_validate(
                json.loads(item["full_market_json"])
            )

            trades, prediction, research = self.execute_prophet_partials(
                market=market,
                research_output=item["analysis"],
                prediction_output=item["prediction_json"],
                research_agent=research_agent,
                prediction_agent=prediction_agent,
            )
            simulated_outcome = False
            if (
                prediction.outcome_prediction
                and prediction.outcome_prediction.probabilities
            ):
                for key in prediction.outcome_prediction.probabilities.keys():
                    if key.lower() == "yes":
                        simulated_outcome = (
                            prediction.outcome_prediction.probabilities[key] > 0.5
                        )
                        break
            market_result = item["market_resolution"].lower() == "yes"
            logger.info(
                f"Trade {index + 1}: Simulated={simulated_outcome}, Actual={market_result}"
            )

            test_result = ProphetTestResult(
                run_name=self.run_name,
                market_question=item["market_question"],
                research=research,
                prediction=prediction,
                trades=trades,
                simulated_outcome=simulated_outcome,
                market_result=market_result,
            )
            results.append(test_result)

        logger.info(
            f"Completed processing {len(results)} trades for {self.mocked_agent_name}"
        )
        return results

    def to_research_output(self, research_output: str) -> Research:
        return Research(
            report=research_output,
            all_queries=[],
            reranked_queries=[],
            websites_to_scrape=[],
            websites_scraped=[],
        )

    def to_prediction_output(self, prediction_output: str) -> PredictionProphet:
        prediction = json.loads(prediction_output)
        return PredictionProphet(
            decision="y" if prediction["p_yes"] > 0.5 else "n",
            p_yes=prediction["p_yes"],
            p_no=prediction["p_no"],
            confidence=prediction["confidence"],
            info_utility=prediction["info_utility"],
            reasoning=prediction["reasoning"],
            logprobs=None,
        )

    def execute_prophet_partials(
        self,
        market: AgentMarket,
        research_output: str,
        prediction_output: str,
        research_agent: Agent,
        prediction_agent: Agent,
    ) -> tuple[list[Trade], Prediction, Research]:
        research = (
            self.prophet_research(research_agent, market.question)
            if self.include_research
            else self.to_research_output(research_output)
        )
        prediction_prophet: PredictionProphet = (
            self.prophet_predict(prediction_agent, market.question, research.report)
            if self.include_prediction
            else self.to_prediction_output(prediction_output)
        )

        probabilistic_answer = ProbabilisticAnswer(
            p_yes=Probability(prediction_prophet.p_yes),
            reasoning=prediction_prophet.reasoning,
            confidence=prediction_prophet.confidence,
        )

        prediction = Prediction(
            outcome_prediction=CategoricalProbabilisticAnswer.from_probabilistic_answer(
                probabilistic_answer
            )
        )

        trades = []
        if prediction.outcome_prediction:
            trades = self.betting_strategy.calculate_trades(
                None,
                prediction.outcome_prediction,
                market,
            )

        return trades, prediction, research

    def evaluate_results(
        self,
        test_results: list[ProphetTestResult],
        print_individual_metrics: bool = False,
    ) -> Dict[str, Any]:
        if not test_results:
            logger.warning("No test results to evaluate")
            return {}

        total_trades = len(test_results)
        logger.info(f"Evaluating {total_trades} test results")

        y_true = [result.market_result for result in test_results]  # Ground truth
        y_pred = [
            result.simulated_outcome for result in test_results
        ]  # Our predictions

        correct_predictions = sum(
            1 for true_val, pred_val in zip(y_true, y_pred) if true_val == pred_val
        )

        accuracy = accuracy_score(y_true, y_pred)
        precision = precision_score(y_true, y_pred, zero_division=0)
        recall = recall_score(y_true, y_pred, zero_division=0)
        f1 = f1_score(y_true, y_pred, zero_division=0)

        metrics = {
            "total_trades": total_trades,
            "correct_predictions": correct_predictions,
            "accuracy": accuracy,
            "precision": precision,
            "recall": recall,
            "f1_score": f1,
            "confusion_matrix": confusion_matrix(y_true, y_pred),
            "classification_report": classification_report(
                y_true, y_pred, target_names=["No", "Yes"]
            ),
        }

        logger.info(
            f"Results: {correct_predictions}/{total_trades} correct predictions ({accuracy:.4f} accuracy)"
        )

        if print_individual_metrics:
            print("\n" + "=" * 50)
            print("EVALUATION METRICS")
            print("=" * 50)
            print(f"Total Trades: {total_trades}")
            print(f"Correct Predictions: {correct_predictions}")
            print(f"Accuracy:  {accuracy:.4f}")
            print(f"Precision: {precision:.4f}")
            print(f"Recall:    {recall:.4f}")
            print(f"F1-Score:  {f1:.4f}")
            print("\nConfusion Matrix:")
            print(metrics["confusion_matrix"])
            print("\nDetailed Classification Report:")
            print(metrics["classification_report"])

        return metrics
