"""
Evolvable Agent - Development tool for testing different combinations of research and prediction functions.

This module provides a flexible framework for experimenting with different agent architectures
by allowing pluggable research and prediction functions.
"""

import typing as t
import json
from functools import partial
from typing import Callable
from prediction_market_agent_tooling.gtypes import Probability
from typing import Any
from pydantic import BaseModel
from pydantic_ai import Agent
from pydantic_ai.models.openai import OpenAIModel
from pydantic_ai.settings import ModelSettings
from prediction_market_agent.tools.openai_utils import get_openai_provider
from prediction_market_agent.utils import APIKeys
from prediction_prophet.benchmark.agents import EmbeddingModel
from prediction_market_agent_tooling.loggers import logger
from prediction_market_agent_tooling.markets.agent_market import AgentMarket
from prediction_market_agent_tooling.markets.omen.omen import OmenAgentMarket
from prediction_market_agent_tooling.markets.seer.seer import SeerAgentMarket
from dataclasses import dataclass
from prediction_prophet.autonolas.research import Prediction as PredictionProphet
from prediction_market_agent_tooling.benchmark.utils import Prediction

from prediction_market_agent_tooling.markets.data_models import ProbabilisticAnswer
from prediction_market_agent.agents.prophet_agent.deploy import DeployablePredictionProphetGPT4oAgent
from prediction_prophet.autonolas.research import make_prediction
from prediction_prophet.functions.research import research, Research
from prediction_market_agent_tooling.deploy.betting_strategy import (
    BettingStrategy,
    KellyBettingStrategy,
)
from prediction_market_agent.agents.utils import get_maximum_possible_bet_amount
from prediction_market_agent_tooling.gtypes import USD
import pandas as pd
from prediction_market_agent_tooling.markets.data_models import (
    CategoricalProbabilisticAnswer,
    ProbabilisticAnswer,
    ExistingPosition,
    Position,
    Trade,
    TradeType,
)
from prediction_market_agent_tooling.tools.utils import check_not_none
from sklearn.metrics import accuracy_score, precision_score, recall_score, f1_score, classification_report, confusion_matrix

GPT_4O_MODEL = "gpt-4o-2024-08-06"
<<<<<<< Updated upstream
DEFAULT_DATASET_PATH = "/home/valden/Work/gnosis/prediction-market-agent/agent_trades_output/DeployablePredictionProphet_2025-05-01_2025-05-14_v1.csv"
=======
DEFAULT_DATASET_PATH = "/home/valden/Work/gnosis/prediction-market-agent/agent_trades_output/DeployablePredictionProphetGPT4oAgent_2025-02-01_2025-03-01.csv"
>>>>>>> Stashed changes


class ProphetTestResult(BaseModel):
    """Pydantic model to store the results of a single prophet agent test."""
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
        mocked_agent_name: str = 'DeployablePredictionProphetGPT4oAgent',
        dataset_path: str = DEFAULT_DATASET_PATH,
        max_trades_to_test_on: int = 10, 
        run_name: str = "test_prophet_agent_baseline",
    ):
        self.prophet_research = prophet_research
        self.prophet_predict = prophet_predict
        self.betting_strategy = betting_strategy
        self.max_trades_to_test_on = max_trades_to_test_on
        self.mocked_agent_name = mocked_agent_name
        self.include_research = include_research
        self.include_prediction = include_prediction
        self.run_name = run_name
        
        api_keys = APIKeys()
        self.research_agent = Agent(
            OpenAIModel(
                GPT_4O_MODEL,
                provider=get_openai_provider(api_key=api_keys.openai_api_key),
            ),
            model_settings=ModelSettings(temperature=0.7),
        )
        self.prediction_agent = Agent(
            OpenAIModel(
                GPT_4O_MODEL,
                provider=get_openai_provider(api_key=api_keys.openai_api_key),
            ),
            model_settings=ModelSettings(temperature=0.0),
        )

        self.dataset = pd.read_csv(dataset_path)


    def test_prophet_agent(self) -> list[ProphetTestResult]:
        filtered_dataset = self.dataset[self.dataset['agent_name'] == self.mocked_agent_name] #Take only trades of simulated agent
        results = []
        for index, item in filtered_dataset.head(self.max_trades_to_test_on).iterrows():
            logger.info(f"Question: {item['market_question']}")
            market = OmenAgentMarket.model_validate(json.loads(item['full_market_json'])) 

            trades, prediction, research = self.execute_prophet_partials(
                market=market,
                research_output=item['analysis'],
                prediction_output=item['prediction_json'] 
            )
            simulated_outcome = prediction.outcome_prediction.probabilities['yes'] > 0.5 if prediction.outcome_prediction else False
            market_result = item['market_resolution'].lower() == 'yes'
            logger.info(f"Simulated outcome: {simulated_outcome}, Ground truth: {market_result}")
            
            # Create and append the test result
            test_result = ProphetTestResult(
                run_name=self.run_name,
                market_question=item['market_question'],
                research=research,
                prediction=prediction,
                trades=trades,
                simulated_outcome=simulated_outcome,
                market_result=market_result
            )
            results.append(test_result)
            
        return results
    
    def to_research_output(self, research_output: str) -> Research:
            return Research(report=research_output, all_queries=[], reranked_queries=[], websites_to_scrape=[], websites_scraped=[])

    def to_prediction_output(self, prediction_output:str) -> PredictionProphet:
        prediction = json.loads(prediction_output)
        return PredictionProphet(
                decision="y" if prediction["p_yes"] > 0.5 else "n",
                p_yes=prediction['p_yes'],
                p_no=prediction['p_no'],
                confidence=prediction['confidence'],
                info_utility=prediction['info_utility'],
                reasoning=prediction['reasoning'],
                logprobs=prediction['logprobs'] if 'logprobs' in prediction else None
            )

    def execute_prophet_partials(
        self,
        market: AgentMarket,
        research_output: str,
        prediction_output: str,
    ) -> tuple[list[Trade], Prediction, Research]:
        research = self.prophet_research(self.research_agent, market.question) if self.include_research else self.to_research_output(research_output)
        prediction_prophet: PredictionProphet = self.prophet_predict(self.prediction_agent, market.question, research.report) if self.include_prediction else self.to_prediction_output(prediction_output)
        
        # Convert PredictionProphet to ProbabilisticAnswer
        probabilistic_answer = ProbabilisticAnswer(
            p_yes=Probability(prediction_prophet.p_yes),
            p_no=Probability(prediction_prophet.p_no),
            reasoning=prediction_prophet.reasoning,
            confidence=prediction_prophet.confidence
        )
        
        prediction = Prediction(
            outcome_prediction=CategoricalProbabilisticAnswer.from_probabilistic_answer(probabilistic_answer)
        )
        
        trades = []
        if prediction.outcome_prediction:
            trades = self.betting_strategy.calculate_trades(
                None,
                prediction.outcome_prediction,
                market,
        )
    
        return trades, prediction, research

    def evaluate_results(self, test_results: list[ProphetTestResult]) -> dict:
        """
        Evaluate the performance of test results using classification metrics.
        
        Args:
            test_results: List of ProphetTestResult objects to evaluate
            
        Returns:
            Dictionary containing evaluation metrics
        """
        if not test_results:
            logger.warning("No test results to evaluate")
            return {}
            
        # Extract predictions and true labels for evaluation
        y_true = [result.market_result for result in test_results]  # Ground truth
        y_pred = [result.simulated_outcome for result in test_results]  # Our predictions
        
        # Calculate evaluation metrics
        accuracy = accuracy_score(y_true, y_pred)
        precision = precision_score(y_true, y_pred, zero_division=0)
        recall = recall_score(y_true, y_pred, zero_division=0)
        f1 = f1_score(y_true, y_pred, zero_division=0)
        
        # Create metrics dictionary
        metrics = {
            'accuracy': accuracy,
            'precision': precision,
            'recall': recall,
            'f1_score': f1,
            'confusion_matrix': confusion_matrix(y_true, y_pred),
            'classification_report': classification_report(y_true, y_pred, target_names=['No', 'Yes'])
        }
        
        # Print evaluation results
        print("\n" + "="*50)
        print("EVALUATION METRICS")
        print("="*50)
        print(f"Accuracy:  {accuracy:.4f}")
        print(f"Precision: {precision:.4f}")
        print(f"Recall:    {recall:.4f}")
        print(f"F1-Score:  {f1:.4f}")
        print("\nConfusion Matrix:")
        print(metrics['confusion_matrix'])
        print("\nDetailed Classification Report:")
        print(metrics['classification_report'])
        
        return metrics


def execute_prophet_research(
    agent: Agent,
    use_summaries: bool = False,
    use_tavily_raw_content: bool = False,
    initial_subqueries_limit: int = 20,
    subqueries_limit: int = 5,
    max_results_per_search: int = 5,
    min_scraped_sites: int = 5,      
) -> partial[Research]:
    return partial(
        research,

    use_summaries=use_summaries,
    use_tavily_raw_content=use_tavily_raw_content,
    initial_subqueries_limit=initial_subqueries_limit,
    subqueries_limit=subqueries_limit, 
    max_results_per_search=max_results_per_search,
    min_scraped_sites=min_scraped_sites,
    logger=logger)

def execute_prophet_predict(agent: Agent, include_reasoning: bool = False) -> partial[PredictionProphet]:
    return partial(make_prediction, include_reasoning=include_reasoning)

if __name__ == "__main__":

    strategy = KellyBettingStrategy(
        max_bet_amount=get_maximum_possible_bet_amount(
            min_=USD(1),
            max_=USD(5),
            trading_balance=USD(40),
        ),
        max_price_impact=0.7,
    )

    tester = ProphetAgentTester(
        prophet_research=execute_prophet_research,
        prophet_predict=execute_prophet_predict,
        betting_strategy=strategy,
        include_research=False,
        include_prediction=False,
        max_trades_to_test_on=3000,
        run_name="test_prophet_agent_BASELINE",
    )
    test_results = tester.test_prophet_agent()



    tester_o3_mini = ProphetAgentTester(
        prophet_research=execute_prophet_research,
        prophet_predict=execute_prophet_predict,
        betting_strategy=strategy,
        include_research=False,
        include_prediction=False,
        max_trades_to_test_on=3000,
<<<<<<< Updated upstream
        run_name="DeployablePredictionProphetGPTo3mini",
        mocked_agent_name="DeployablePredictionProphetGPTo3mini",
=======
        run_name="DeployablePredictionProphetGPT4oAgent_B",
        mocked_agent_name="DeployablePredictionProphetGPT4oAgent_B",
>>>>>>> Stashed changes
    )
    test_results_o3_mini = tester_o3_mini.test_prophet_agent()

    logger.info("Testing baseline agent")
    evaluation_metrics = tester.evaluate_results(test_results)

    logger.info("Testing O3 mini agent")
    evaluation_metrics_o3_mini = tester_o3_mini.evaluate_results(test_results_o3_mini)
    
    


    

