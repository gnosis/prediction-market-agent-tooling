import json
import os
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import pandas as pd
import typer
from langfuse import Langfuse
from langfuse.client import TraceWithDetails
from pydantic import BaseModel

from prediction_market_agent_tooling.config import APIKeys
from prediction_market_agent_tooling.gtypes import DatetimeUTC, OutcomeStr, OutcomeToken
from prediction_market_agent_tooling.loggers import logger
from prediction_market_agent_tooling.markets.agent_market import AgentMarket
from prediction_market_agent_tooling.markets.data_models import Resolution
from prediction_market_agent_tooling.markets.markets import MarketType
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

PREDICTION_STATES = [
    "predict_market",
    "_make_prediction_categorical",
    "make_prediction",
]
REPORT_STATES = ["prepare_report"]

TRADE_STATES = ["build_trades"]

MARKET_RESOLUTION_PROVIDERS = {
    MarketType.OMEN: lambda market_id: OmenAgentMarket.get_binary_market(market_id),
    MarketType.SEER: lambda market_id: SeerAgentMarket.from_data_model_with_subgraph(
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
    prediction_confidence: float
    market_resolution: str | None
    resolution_is_valid: bool | None
    full_market_json: str | None
    prediction_json: str
    trades: list[dict[str, Any]] | None


def get_langfuse_client() -> Langfuse:
    api_keys = APIKeys()
    return Langfuse(
        secret_key=api_keys.langfuse_secret_key.get_secret_value(),
        public_key=api_keys.langfuse_public_key,
        host=api_keys.langfuse_host,
        httpx_client=HttpxCachedClient().get_client(),
    )


def create_output_file_path(
    agent_name: str,
    date_from: DatetimeUTC,
    date_to: DatetimeUTC,
    output_folder: str,
) -> str:
    """Create unique output file path, incrementing version if file exists."""
    Path(output_folder).mkdir(parents=True, exist_ok=True)

    default_file_name = f"{agent_name}_{date_from.date()}_{date_to.date()}"
    output_file = os.path.join(output_folder, f"{default_file_name}.csv")

    index = 0
    while os.path.exists(output_file):
        index += 1
        output_file = os.path.join(output_folder, f"{default_file_name}_v{index}.csv")

    return output_file


def download_data_daily(
    agent_name: str,
    date_from: DatetimeUTC,
    date_to: DatetimeUTC,
    only_resolved: bool,
    output_file: str,
    append_mode: bool = False,
) -> tuple[int, int]:
    """Download data for a single day/period and return (traces_downloaded, records_saved)."""
    langfuse_client_for_traces = get_langfuse_client()

    logger.info(f"Processing data for {date_from.date()} to {date_to.date()}")

    traces = get_traces_for_agent(
        agent_name=agent_name,
        trace_name="process_market",
        from_timestamp=date_from,
        to_timestamp=date_to,
        has_output=True,
        client=langfuse_client_for_traces,
        tags=["answered"],
    )

    traces_count = len(traces) if traces else 0
    if not traces:
        logger.info(f"No traces found for {date_from.date()}")
        # If this is the first call and no traces, create empty CSV with header
        if not append_mode:
            df_empty = pd.DataFrame(columns=list(TraceResult.model_fields.keys()))
            df_empty.to_csv(output_file, mode="w", header=True, index=False)
        return 0, 0

    # Use ThreadPoolExecutor with shared client (thread-safe)
    results = []
    with ThreadPoolExecutor(max_workers=3) as executor:
        # Submit all tasks
        future_to_trace = {
            executor.submit(
                process_trace, trace, only_resolved, langfuse_client_for_traces
            ): trace
            for trace in traces
        }

        # Collect results as they complete
        for future in as_completed(future_to_trace):
            try:
                result = future.result()
                results.append(result)
            except Exception as e:
                trace = future_to_trace[future]
                logger.exception(f"Error processing trace {trace.id}: {e}")
                results.append(None)

    successful_results = [r for r in results if r is not None]
    if successful_results:
        results_data = [result.model_dump() for result in successful_results]
        df = pd.DataFrame(results_data)

        df.to_csv(
            output_file,
            mode="a" if append_mode else "w",
            header=not append_mode,
            index=False,
        )
        logger.info(f"Saved {len(successful_results)} records for {date_from.date()}")
    elif not append_mode:
        df_empty = pd.DataFrame(columns=list(TraceResult.model_fields.keys()))
        df_empty.to_csv(output_file, mode="w", header=True, index=False)

    return traces_count, len(successful_results)


def download_data(
    agent_name: str,
    date_from: DatetimeUTC,
    date_to: DatetimeUTC,
    only_resolved: bool,
    output_folder: str,
) -> None:
    output_file = create_output_file_path(agent_name, date_from, date_to, output_folder)
    total_traces = 0
    total_saved = 0
    daily_stats = []

    current_date = date_from
    first_call = True

    while current_date < date_to:
        next_date = DatetimeUTC.from_datetime(current_date + timedelta(days=1))
        if next_date > date_to:
            next_date = date_to

        traces_downloaded, records_saved = download_data_daily(
            agent_name=agent_name,
            date_from=current_date,
            date_to=next_date,
            only_resolved=only_resolved,
            output_file=output_file,
            append_mode=not first_call,
        )

        daily_stats.append(
            {
                "date": current_date.date(),
                "traces_downloaded": traces_downloaded,
                "records_saved": records_saved,
            }
        )

        total_traces += traces_downloaded
        total_saved += records_saved
        first_call = False
        current_date = next_date

    # Print daily report
    logger.info("=" * 60)
    logger.info("DAILY PROCESSING REPORT")
    logger.info("=" * 60)
    for stats in daily_stats:
        total_traces_downloaded = int(stats["traces_downloaded"])  # type: ignore
        total_records_saved = int(stats["records_saved"])  # type: ignore
        success_rate = (
            (total_records_saved / total_traces_downloaded * 100)
            if total_traces_downloaded > 0
            else 0
        )
        logger.info(
            f"{stats['date']}: {total_traces_downloaded} traces downloaded, {total_records_saved} successfully processed ({success_rate:.1f}%)"
        )

    logger.info("=" * 60)
    logger.info("OVERALL SUMMARY")
    logger.info("=" * 60)
    overall_success_rate = (total_saved / total_traces * 100) if total_traces > 0 else 0
    logger.info(f"Total traces downloaded: {total_traces}")
    logger.info(f"Total records saved: {total_saved}")
    logger.info(f"Overall success rate: {overall_success_rate:.1f}%")

    if total_saved == 0:
        logger.warning("No results to save")
    else:
        logger.info(f"Output file: {output_file}")
    logger.info("=" * 60)


def process_trace(
    trace: TraceWithDetails,
    only_resolved: bool,
    langfuse_client: Langfuse,
    include_market: bool = True,
) -> TraceResult | None:
    try:
        logger.info(f"Processing trace {trace.id}")
        observations = langfuse_client.fetch_observations(trace_id=trace.id)
        logger.info(f"Observations downloaded for trace {trace.id}")
        market_state, market_type = get_agent_market_state(trace.input)

        prepare_report_obs = [
            obs for obs in observations.data if obs.name in REPORT_STATES
        ]
        predict_market_obs = [
            obs for obs in observations.data if obs.name in PREDICTION_STATES
        ]
        build_trades_obs = [
            obs for obs in observations.data if obs.name in TRADE_STATES
        ]
        if not prepare_report_obs or not predict_market_obs:
            raise ValueError(f"Missing required observations for trace {trace.id}")

        analysis = prepare_report_obs[0].output
        prediction = predict_market_obs[0].output

        resolution = get_market_resolution(market_state.id, market_type)

        if only_resolved and not resolution:
            raise ValueError(f"No resolution found for market {market_state.id}")

        result = TraceResult(
            agent_name=trace.metadata["agent_class"],
            trace_id=trace.id,
            market_id=market_state.id,
            market_type=market_type.value,
            market_question=market_state.question,
            market_outcomes=list(market_state.outcomes),
            market_outcome_token_pool=market_state.outcome_token_pool,
            market_created_time=market_state.created_time,
            market_close_time=market_state.close_time,
            analysis=analysis,
            prediction_reasoning=prediction["reasoning"],
            prediction_decision="y" if prediction["p_yes"] > 0.5 else "n",
            prediction_p_yes=prediction["p_yes"],
            prediction_info_utility=prediction["info_utility"],
            prediction_confidence=prediction["confidence"],
            prediction_json=json.dumps(prediction),
            market_resolution=resolution.outcome if resolution else None,
            resolution_is_valid=not resolution.invalid if resolution else None,
            full_market_json=market_state.model_dump_json() if include_market else None,
            trades=build_trades_obs[0].output if build_trades_obs else None,
        )
        logger.info(f"Downloaded trace {trace.id} finished")
        return result

    except Exception as e:
        logger.exception(f"Error processing trace {trace.id}: {e}")
        return None


def get_agent_market_state(
    input_data: dict[str, Any]
) -> tuple[AgentMarket, MarketType]:
    if not input_data or "args" not in input_data:
        raise ValueError("Invalid input data: missing args")

    args = input_data["args"]
    if len(args) < 2:
        raise ValueError("Invalid args: expected at least 2 elements")

    market_type = MarketType(args[0])
    if market_type not in MARKET_RESOLUTION_PROVIDERS:
        raise ValueError(f"Unknown market type: {market_type}")

    market_data = args[1]  # market object data

    # recreate probabilities if not present
    if "outcome_token_pool" in market_data and "probabilities" not in market_data:
        market_data["probabilities"] = AgentMarket.build_probability_map(
            [
                OutcomeToken(
                    float(value["value"]) if isinstance(value, dict) else float(value)
                ).as_outcome_wei
                for value in market_data["outcome_token_pool"].values()
            ],
            list(market_data["outcome_token_pool"].keys()),
        )

    if market_type == MarketType.OMEN:
        return OmenAgentMarket.model_validate(market_data), market_type
    elif market_type == MarketType.SEER:
        return SeerAgentMarket.model_validate(market_data), market_type
    else:
        return AgentMarket.model_validate(market_data), market_type


def get_market_resolution(market_id: str, market_type: MarketType) -> Resolution:
    if market_type not in MARKET_RESOLUTION_PROVIDERS:
        raise ValueError(f"Unknown market type: {market_type.market_class}")

    try:
        market: AgentMarket | None = MARKET_RESOLUTION_PROVIDERS[market_type](market_id)

        if not market or not market.resolution:
            raise ValueError(f"No resolution found for market: {market_id}")

        return market.resolution

    except Exception as e:
        raise ValueError(
            f"Failed to fetch {market_type.market_class} market {market_id} resolution: {e}"
        ) from e


def parse_date(date_str: str, param_name: str) -> DatetimeUTC:
    try:
        return DatetimeUTC.to_datetime_utc(date_str)
    except ValueError as e:
        typer.echo(f"Error: Invalid date format for {param_name}: {date_str}")
        typer.echo("Expected format: YYYY-MM-DD or YYYY-MM-DDTHH:MM:SS")
        raise typer.Exit(1) from e


def main(
    agent_name: str = "DeployablePredictionProphet",
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
