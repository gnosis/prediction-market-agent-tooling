from functools import partial
from typing import Any, Dict

import pandas as pd
import typer
from prediction_market_agent.agents.utils import get_maximum_possible_bet_amount
from prediction_market_agent.tools.openai_utils import get_openai_provider
from prediction_market_agent.utils import APIKeys
from prediction_prophet.autonolas.research import Prediction as PredictionProphet
from prediction_prophet.autonolas.research import make_prediction
from prediction_prophet.functions.research import Research, research
from pydantic_ai import Agent
from pydantic_ai.models.openai import OpenAIModel
from pydantic_ai.settings import ModelSettings

from prediction_market_agent_tooling.agent.development_tools.prophet_agent_tester import (
    ProphetAgentTester,
    ProphetTestResult,
)
from prediction_market_agent_tooling.deploy.betting_strategy import KellyBettingStrategy
from prediction_market_agent_tooling.gtypes import USD
from prediction_market_agent_tooling.loggers import logger

GPT_4O_MODEL = "gpt-4o-2024-08-06"


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
        logger=logger,
    )


def execute_prophet_predict(
    agent: Agent, include_reasoning: bool = False
) -> partial[PredictionProphet]:
    return partial(make_prediction, include_reasoning=include_reasoning)


def test_all_models(
    dataset_path: str,
    max_trades_to_test_on: int = 3000,
    delay_between_trades: float = 2.0,
    max_bet_amount_min: USD = USD(1),
    max_bet_amount_max: USD = USD(5),
    trading_balance: USD = USD(40),
    max_price_impact: float = 0.7,
    include_research: bool = False,
    include_prediction: bool = False,
) -> tuple[Dict[str, list[ProphetTestResult]], Dict[str, Dict[str, Any]]]:
    dataset = pd.read_csv(dataset_path)

    agent_names = dataset["agent_name"].unique().tolist()
    total_agents = len(agent_names)
    logger.info(f"Found {total_agents} agents in dataset: {agent_names}")

    api_keys = APIKeys()
    research_agent = Agent(
        OpenAIModel(
            GPT_4O_MODEL,
            provider=get_openai_provider(api_key=api_keys.openai_api_key),
        ),
        model_settings=ModelSettings(temperature=0.7),
    )
    prediction_agent = Agent(
        OpenAIModel(
            GPT_4O_MODEL,
            provider=get_openai_provider(api_key=api_keys.openai_api_key),
        ),
        model_settings=ModelSettings(temperature=0.0),
    )

    strategy = KellyBettingStrategy(
        max_bet_amount=get_maximum_possible_bet_amount(
            min_=max_bet_amount_min,
            max_=max_bet_amount_max,
            trading_balance=trading_balance,
        ),
        max_price_impact=max_price_impact,
    )

    all_results, all_metrics = {}, {}
    for agent_index, agent_name in enumerate(agent_names, 1):
        logger.info(f"Testing agent {agent_index}/{total_agents}: {agent_name}")

        tester = ProphetAgentTester(
            prophet_research=execute_prophet_research(research_agent),
            prophet_predict=execute_prophet_predict(prediction_agent),
            betting_strategy=strategy,
            include_research=include_research,
            include_prediction=include_prediction,
            max_trades_to_test_on=max_trades_to_test_on,
            run_name=f"test_{agent_name}",
            mocked_agent_name=agent_name,
            delay_between_trades=delay_between_trades,
        )

        test_results = tester.test_prophet_agent(
            dataset, research_agent, prediction_agent
        )
        evaluation_metrics = tester.evaluate_results(test_results)

        all_results[agent_name] = test_results
        all_metrics[agent_name] = evaluation_metrics

        trades_processed = len(test_results)
        logger.info(
            f"Completed testing for {agent_name}: {trades_processed} trades processed"
        )

    logger.info("\n" + "=" * 60)
    logger.info("SUMMARY")
    logger.info("=" * 60)

    total_trades_processed = 0
    for agent_index, agent_name in enumerate(agent_names, 1):
        metrics = all_metrics[agent_name]
        trades_count = len(all_results[agent_name])
        total_trades_processed += trades_count

        if metrics:
            logger.info(f"{agent_index}. {agent_name} ({trades_count} trades):")
            logger.info(f"   Accuracy: {metrics.get('accuracy', 'N/A'):.4f}")
            logger.info(f"   F1-Score: {metrics.get('f1_score', 'N/A'):.4f}")
            logger.info(f"   Precision: {metrics.get('precision', 'N/A'):.4f}")
            logger.info(f"   Recall: {metrics.get('recall', 'N/A'):.4f}")
        else:
            logger.info(
                f"{agent_index}. {agent_name} ({trades_count} trades): No metrics available"
            )

    logger.info(
        f"\nTotal: {total_agents} agents tested, {total_trades_processed} total trades processed"
    )

    return all_results, all_metrics


def main(
    dataset_path: str = typer.Argument(..., help="Path to the CSV dataset file"),
    max_trades: int = typer.Option(
        3000, "--max-trades", help="Maximum number of trades to test per agent"
    ),
    delay: float = typer.Option(
        2.0, "--delay", help="Delay in seconds between processing each trade"
    ),
    min_bet: float = typer.Option(1.0, "--min-bet", help="Minimum bet amount"),
    max_bet: float = typer.Option(5.0, "--max-bet", help="Maximum bet amount"),
    balance: float = typer.Option(40.0, "--balance", help="Total trading balance"),
    max_impact: float = typer.Option(0.7, "--max-impact", help="Maximum price impact"),
    research: bool = typer.Option(
        False, "--research", help="Include research generation"
    ),
    prediction: bool = typer.Option(
        False, "--prediction", help="Include prediction generation"
    ),
) -> None:
    logger.info(f"Starting agent testing with dataset: {dataset_path}")

    all_results, all_metrics = test_all_models(
        dataset_path=dataset_path,
        max_trades_to_test_on=max_trades,
        delay_between_trades=delay,
        max_bet_amount_min=USD(min_bet),
        max_bet_amount_max=USD(max_bet),
        trading_balance=USD(balance),
        max_price_impact=max_impact,
        include_research=research,
        include_prediction=prediction,
    )

    logger.info("Testing completed successfully!")


if __name__ == "__main__":
    typer.run(main)
