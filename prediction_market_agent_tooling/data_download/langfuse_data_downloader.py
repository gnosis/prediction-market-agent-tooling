import os
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import pandas as pd
import typer
from langfuse import Langfuse
from langfuse.client import TraceWithDetails
from pydantic import BaseModel

from prediction_market_agent_tooling.config import APIKeys
from prediction_market_agent_tooling.gtypes import (
    DatetimeUTC,
    OutcomeStr,
    OutcomeToken,
)
from prediction_market_agent_tooling.loggers import logger
from prediction_market_agent_tooling.markets.agent_market import AgentMarket
from prediction_market_agent_tooling.markets.data_models import Resolution
from prediction_market_agent_tooling.markets.omen.omen import OmenAgentMarket
from prediction_market_agent_tooling.markets.seer.seer import SeerAgentMarket
from prediction_market_agent_tooling.markets.seer.seer_subgraph_handler import (
    SeerSubgraphHandler,
)
from prediction_market_agent_tooling.tools.hexbytes_custom import HexBytes
from prediction_market_agent_tooling.tools.httpx_cached_client import HttpxCachedClient
from prediction_market_agent_tooling.tools.langfuse_client_utils import (
    get_traces_for_agent,
)
from prediction_market_agent_tooling.tools.parallelism import par_map

PREDICTION_STATES = [
    "predict_market",
    "_make_prediction_categorical",
    "make_prediction",
]
REPORT_STATES = ["prepare_report"]

MARKET_RESOLUTION_PROVIDERS = {
    "omen": lambda market_id: OmenAgentMarket.get_binary_market(market_id),
    "seer": lambda market_id: SeerAgentMarket.from_data_model_with_subgraph(
        model=SeerSubgraphHandler().get_market_by_id(HexBytes(market_id)),
        seer_subgraph=SeerSubgraphHandler(),
        must_have_prices=False,
    ),
}


class TraceResult(BaseModel):
    agent_name: str
    trace_id: str
    market_id: str
    market_type: str
    market_question: str
    market_outcomes: list[str]
    market_outcome_token_pool: dict[OutcomeStr, OutcomeToken] | None
    market_created_time: DatetimeUTC | None
    market_close_time: DatetimeUTC | None
    analysis: str
    prediction_reasoning: str
    prediction_decision: str
    prediction_p_yes: float
    prediction_info_utility: float
    market_resolution: str | None
    resolution_is_valid: bool | None


def get_langfuse_client() -> Langfuse:
    api_keys = APIKeys()
    return Langfuse(
        secret_key=api_keys.langfuse_secret_key.get_secret_value(),
        public_key=api_keys.langfuse_public_key,
        host=api_keys.langfuse_host,
        httpx_client=HttpxCachedClient().get_client(),
    )


def download_data(
    agent_name: str,
    date_from: DatetimeUTC,
    date_to: DatetimeUTC,
    only_resolved: bool,
    output_folder: str,
) -> None:
    Path(output_folder).mkdir(parents=True, exist_ok=True)
    index = 0
    default_file_name = f"{agent_name}_{date_from.date()}_{date_to.date()}"
    output_file = os.path.join(output_folder, f"{default_file_name}.csv")

    if os.path.exists(output_file):
        while os.path.exists(output_file):
            index += 1
            output_file = os.path.join(
                output_folder, f"{default_file_name}_v{index}.csv"
            )

    langfuse_client_for_traces = get_langfuse_client()

    traces = get_traces_for_agent(
        agent_name=agent_name,
        trace_name="process_market",
        from_timestamp=date_from,
        to_timestamp=date_to,
        has_output=True,
        client=langfuse_client_for_traces,
        tags=["answered"],
    )

    if not traces:
        raise ValueError("No traces found for the specified criteria")

    trace_args = [
        (
            trace,
            only_resolved,
        )
        for trace in traces
    ]

    results = par_map(
        items=trace_args,
        func=lambda args: process_trace(*args),
        max_workers=5,
    )

    successful_results = [r for r in results if r is not None]
    if successful_results:
        results_data = [result.model_dump() for result in successful_results]
        pd.DataFrame(results_data).to_csv(output_file, index=False)
        logger.info(f"Saved {len(successful_results)} records to {output_file}")
    else:
        logger.warning("No results to save")


def process_trace(
    trace: TraceWithDetails,
    only_resolved: bool,
) -> TraceResult | None:
    langfuse_client = get_langfuse_client()
    try:
        observations = langfuse_client.fetch_observations(trace_id=trace.id)

        market_state, market_type = get_agent_market_state(trace.input)

        prepare_report_obs = [
            obs for obs in observations.data if obs.name in REPORT_STATES
        ]
        predict_market_obs = [
            obs for obs in observations.data if obs.name in PREDICTION_STATES
        ]

        if not prepare_report_obs or not predict_market_obs:
            raise ValueError(f"Missing required observations for trace {trace.id}")

        analysis = prepare_report_obs[0].output
        prediction = predict_market_obs[0].output

        resolution = get_market_resolution(market_state.id, market_type)

        if only_resolved and not resolution:
            raise ValueError(f"No resolution found for market {market_state.id}")

        result = TraceResult(
            agent_name=trace.metadata.get("agent_class", "unknown"),
            trace_id=trace.id,
            market_id=market_state.id,
            market_type=market_type,
            market_question=market_state.question,
            market_outcomes=list(market_state.outcomes),
            market_outcome_token_pool=market_state.outcome_token_pool,
            market_created_time=market_state.created_time,
            market_close_time=market_state.close_time,
            analysis=analysis,
            prediction_reasoning=prediction["reasoning"],
            prediction_decision="YES" if prediction["decision"] == "y" else "NO",
            prediction_p_yes=prediction["p_yes"],
            prediction_info_utility=prediction["info_utility"],
            market_resolution=resolution.outcome if resolution else None,
            resolution_is_valid=not resolution.invalid if resolution else None,
        )

        return result

    except Exception as e:
        logger.error(f"Error processing trace {trace.id}: {e}", exc_info=True)
        return None


def get_agent_market_state(input_data: dict[str, Any]) -> tuple[AgentMarket, str]:
    if not input_data or "args" not in input_data:
        raise ValueError("Invalid input data: missing args")

    args = input_data["args"]
    if len(args) < 2:
        raise ValueError("Invalid args: expected at least 2 elements")

    market_type = args[0]  # e.g., "omen", "seer"

    if market_type not in MARKET_RESOLUTION_PROVIDERS:
        raise ValueError(f"Unknown market type: {market_type}")

    market_data = args[1]  # market object data
    market_state = AgentMarket.model_construct(**market_data)

    return market_state, market_type


def get_market_resolution(market_id: str, market_type: str) -> Resolution:
    market_type_lower = market_type.lower()

    if market_type_lower not in MARKET_RESOLUTION_PROVIDERS:
        raise ValueError(f"Unknown market type: {market_type}")

    try:
        market: AgentMarket | None = MARKET_RESOLUTION_PROVIDERS[market_type_lower](
            market_id
        )

        if not market or not market.resolution:
            raise ValueError(f"No resolution found for market: {market_id}")

        return market.resolution

    except Exception as e:
        raise ValueError(
            f"Failed to fetch {market_type} market {market_id} resolution: {e}"
        ) from e


def parse_date(date_str: str, param_name: str) -> DatetimeUTC:
    try:
        return DatetimeUTC.from_datetime(datetime.fromisoformat(date_str))
    except ValueError:
        typer.echo(f"Error: Invalid date format for {param_name}: {date_str}")
        typer.echo("Expected format: YYYY-MM-DD or YYYY-MM-DDTHH:MM:SS")
        raise typer.Exit(1) from e


def main(
    agent_name: str = "DeployablePredictionProphetGPT4oAgent",
    only_resolved: bool = True,
    date_from: str = typer.Option(
        None, help="Start date in ISO format (YYYY-MM-DD or YYYY-MM-DDTHH:MM:SS)"
    ),
    date_to: str = typer.Option(
        None, help="End date in ISO format (YYYY-MM-DD or YYYY-MM-DDTHH:MM:SS)"
    ),
    output_folder: str = "./agent_trades_output/",
) -> None:
    date_from_dt = (
        parse_date(date_from, "date_from")
        if date_from
        else DatetimeUTC.from_datetime(datetime.now() - timedelta(days=1))
    )
    date_to_dt = (
        parse_date(date_to, "date_to")
        if date_to
        else DatetimeUTC.from_datetime(datetime.now())
    )

    download_data(
        agent_name=agent_name,
        date_from=date_from_dt,
        date_to=date_to_dt,
        only_resolved=only_resolved,
        output_folder=output_folder,
    )


if __name__ == "__main__":
    typer.run(main)
