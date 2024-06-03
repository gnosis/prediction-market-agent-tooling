import json
import os
import typing as t
from itertools import groupby

import altair as alt
import numpy as np
import pandas as pd
import streamlit as st
from google.cloud.functions_v2.types.functions import Function
from pydantic import BaseModel, field_validator

from prediction_market_agent_tooling.config import APIKeys
from prediction_market_agent_tooling.deploy.gcp.kubernetes_models import (
    KubernetesCronJob,
)
from prediction_market_agent_tooling.deploy.gcp.utils import (
    gcp_get_secret_value,
    get_gcp_configmap_data,
    get_gcp_function,
    list_gcp_cronjobs,
    list_gcp_functions,
)
from prediction_market_agent_tooling.loggers import logger
from prediction_market_agent_tooling.markets.agent_market import AgentMarket
from prediction_market_agent_tooling.markets.data_models import Resolution, ResolvedBet
from prediction_market_agent_tooling.tools.parallelism import par_map
from prediction_market_agent_tooling.tools.utils import (
    DatetimeWithTimezone,
    add_utc_timezone_validator,
    check_not_none,
    should_not_happen,
)

C = t.TypeVar("C", bound="DeployedAgent")


class DeployedAgent(BaseModel):
    PREFIX: t.ClassVar["str"] = "deployedagent_var_"

    name: str

    start_time: DatetimeWithTimezone
    end_time: t.Optional[DatetimeWithTimezone] = (
        None  # TODO: If we want end time, we need to store agents somewhere, not just query them from functions.
    )

    raw_labels: dict[str, str] | None = None
    raw_env_vars: dict[str, str] | None = None

    _add_timezone_validator_start_time = field_validator("start_time")(
        add_utc_timezone_validator
    )
    _add_timezone_validator_end_time = field_validator("end_time")(
        add_utc_timezone_validator
    )

    def model_dump_prefixed(self) -> dict[str, t.Any]:
        return {
            self.PREFIX + k: v for k, v in self.model_dump().items() if v is not None
        }

    def get_resolved_bets(self) -> list[ResolvedBet]:
        raise NotImplementedError("Subclasses must implement this method.")

    @property
    def public_id(self) -> str:
        raise NotImplementedError("Subclasses must implement this method.")

    @classmethod
    def from_env_vars_without_prefix(
        cls: t.Type[C],
        env_vars: dict[str, t.Any] | None = None,
        extra_vars: dict[str, t.Any] | None = None,
    ) -> C:
        return cls.model_validate((env_vars or dict(os.environ)) | (extra_vars or {}))

    @classmethod
    def from_env_vars(
        cls: t.Type[C],
        env_vars: dict[str, t.Any] | None = None,
        extra_vars: dict[str, t.Any] | None = None,
    ) -> C:
        return cls.from_env_vars_without_prefix(
            env_vars={
                k.replace(cls.PREFIX, ""): v
                for k, v in (env_vars or dict(os.environ)).items()
                if k.startswith(cls.PREFIX)
            },
            extra_vars=extra_vars,
        )

    @staticmethod
    def from_api_keys(
        name: str,
        start_time: DatetimeWithTimezone,
        api_keys: APIKeys,
    ) -> "DeployedAgent":
        raise NotImplementedError("Subclasses must implement this method.")

    @classmethod
    def from_gcp_function(cls: t.Type[C], function: Function) -> C:
        return cls.from_env_vars_without_prefix(
            env_vars=dict(function.service_config.environment_variables),
            extra_vars={
                "raw_labels": dict(function.labels),
                "raw_env_vars": dict(function.service_config.environment_variables),
            },
        )

    @classmethod
    def from_gcp_function_name(cls: t.Type[C], function_name: str) -> C:
        return cls.from_gcp_function(get_gcp_function(function_name))

    @classmethod
    def from_all_gcp_functions(
        cls: t.Type[C], filter_: t.Callable[[Function], bool] = lambda x: True
    ) -> t.Sequence[C]:
        agents: list[C] = []

        for function in list_gcp_functions():
            if not filter_(function):
                continue

            logger.info(f"Loading function: {function.name}")

            try:
                agents.append(cls.from_gcp_function(function))
            except ValueError as e:
                logger.warning(
                    f"Could not parse `{function.name}` into {cls.__name__}: {e}."
                )

        return agents

    @classmethod
    def from_gcp_cronjob(cls: t.Type[C], cronjob: KubernetesCronJob) -> C:
        secret_env_name_to_env_value = {
            e.name: json.loads(gcp_get_secret_value(e.valueFrom.secretKeyRef.name))[
                e.valueFrom.secretKeyRef.key
            ]
            for e in cronjob.spec.jobTemplate.spec.template.spec.containers[0].env
        }
        configmap_env_name_to_env_value = {
            key: value
            for e in cronjob.spec.jobTemplate.spec.template.spec.containers[0].envFrom
            for key, value in get_gcp_configmap_data(
                cronjob.metadata.namespace, e.configMapRef.name
            ).items()
        }

        return cls.from_env_vars_without_prefix(
            env_vars=secret_env_name_to_env_value | configmap_env_name_to_env_value,
        )

    @classmethod
    def from_all_gcp_cronjobs(
        cls: t.Type[C],
        namespace: str,
        filter_: t.Callable[[KubernetesCronJob], bool] = lambda x: True,
    ) -> t.Sequence[C]:
        agents: list[C] = []

        for cronjob in list_gcp_cronjobs(namespace).items:
            if not filter_(cronjob):
                continue

            logger.info(f"Loading cronjob: {cronjob.metadata.name}")

            try:
                agents.append(cls.from_gcp_cronjob(cronjob))
            except ValueError as e:
                logger.warning(
                    f"Could not parse `{cronjob.metadata.name}` into {cls.__name__}: {e}."
                )

        return agents


def monitor_agent(agent: DeployedAgent) -> None:
    # Info
    col1, col2, col3 = st.columns(3)
    col1.markdown(f"Name: `{agent.name}`")
    col2.markdown(f"Start Time: `{agent.start_time}`")
    col3.markdown(f"Public ID: `{agent.public_id}`")

    show_agent_bets = st.checkbox(
        "Show resolved bets statistics", value=False, key=f"{agent.name}_show_bets"
    )
    if not show_agent_bets:
        return

    agent_bets = agent.get_resolved_bets()
    if not agent_bets:
        st.warning(f"No resolved bets found for {agent.name}.")
        return
    bets_info = {
        "Market Question": [bet.market_question for bet in agent_bets],
        "Bet Amount": [bet.amount.amount for bet in agent_bets],
        "Bet Outcome": [bet.outcome for bet in agent_bets],
        "Created Time": [bet.created_time for bet in agent_bets],
        "Resolved Time": [bet.resolved_time for bet in agent_bets],
        "Is Correct": [bet.is_correct for bet in agent_bets],
        "Profit": [round(bet.profit.amount, 2) for bet in agent_bets],
    }
    bets_df = pd.DataFrame(bets_info).sort_values(by="Resolved Time", ascending=False)

    # Metrics
    col1, col2 = st.columns(2)
    col1.metric(label="Number of bets", value=f"{len(agent_bets)}")
    col2.metric(label="% Correct", value=f"{100 * bets_df['Is Correct'].mean():.2f}%")

    # Time column to use for x-axes
    x_axis_column = st.selectbox(
        "X-axis column",
        ["Created Time", "Resolved Time"],
        key=f"{agent.name}_x_axis_column",
    )

    # Chart of grouped accuracy per day
    bets_df["x-axis-day"] = bets_df[x_axis_column].dt.date
    per_day_accuracy = bets_df.groupby("x-axis-day")["Is Correct"].mean()
    per_day_accuracy_chart = (
        alt.Chart(per_day_accuracy.reset_index())
        .encode(
            x=alt.X("x-axis-day", axis=alt.Axis(format="%Y-%m-%d"), title=None),
            y=alt.Y("Is Correct", axis=alt.Axis(format=".2f")),
        )
        .interactive()
    )
    st.altair_chart(
        per_day_accuracy_chart.mark_line()
        + per_day_accuracy_chart.transform_loess("x-axis-day", "Is Correct").mark_line(
            color="red", strokeDash=[5, 5]
        ),
        use_container_width=True,
    )

    # Chart of cumulative profit per day
    profit_info = {
        "Time": bets_df[x_axis_column],
        "Cumulative Profit": bets_df["Profit"].astype(float),
    }
    profit_df = pd.DataFrame(profit_info)
    profit_df["Date"] = pd.to_datetime(profit_df["Time"].dt.date)
    profit_df = (
        profit_df.groupby("Date")["Cumulative Profit"].sum().cumsum().reset_index()
    )
    profit_df["Cumulative Profit"] = profit_df["Cumulative Profit"].astype(float)
    st.altair_chart(
        alt.Chart(profit_df)
        .mark_line()
        .encode(
            x=alt.X("Date", axis=alt.Axis(format="%Y-%m-%d"), title=None),
            y=alt.Y("Cumulative Profit", axis=alt.Axis(format=".2f")),
        )
        .interactive(),
        use_container_width=True,
    )

    # Table of resolved bets
    show_bet_history = st.checkbox(
        "Show resolved bet history", value=False, key=f"{agent.name}_show_bet_history"
    )
    if show_bet_history:
        st.subheader("Resolved Bet History")
        st.table(bets_df)


def monitor_market(
    open_markets: t.Sequence[AgentMarket], resolved_markets: t.Sequence[AgentMarket]
) -> None:
    col1, col2 = st.columns(2)
    col1.metric(label="Number open markets", value=f"{len(open_markets)}")
    col2.metric(label="Number resolved markets", value=f"{len(resolved_markets)}")

    monitor_brier_score(resolved_markets)
    monitor_market_outcome_bias(open_markets, resolved_markets)


def monitor_brier_score(resolved_markets: t.Sequence[AgentMarket]) -> None:
    """
    https://en.wikipedia.org/wiki/Brier_score

    Calculate the Brier score for the resolved markets. Display a chart of the
    rolling mean squared error for, and stats for:

    - the overall brier score
    - the brier score for the last 30 markets
    """
    st.subheader("Brier Score (0-2, lower is better)")

    # We need to use `get_last_trade_p_yes` instead of `current_p_yes` because, for resolved markets, the probabilities can be fixed to 0 and 1 (for example, on Omen).
    # And for the brier score, we need the true market prediction, not its resolution after the outcome is known.
    # If no trades were made, take it as 0.5 because the platform didn't provide any valuable information.
    created_time_and_squared_errors_summed_across_outcomes = par_map(
        list(resolved_markets),
        lambda m: (
            m.created_time,
            (
                (p_yes - m.boolean_outcome) ** 2
                + ((1 - p_yes) - (1 - m.boolean_outcome)) ** 2
                if (p_yes := m.get_last_trade_p_yes()) is not None
                else None
            ),
        ),
    )
    created_time_and_squared_errors_summed_across_outcomes_with_trades = [
        x
        for x in created_time_and_squared_errors_summed_across_outcomes
        if x[1] is not None
    ]
    df = pd.DataFrame(
        created_time_and_squared_errors_summed_across_outcomes_with_trades,
        columns=["Date", "Squared Error"],
    ).sort_values(by="Date")

    # Compute rolling mean squared error for last 30 markets
    df["Rolling Mean Squared Error"] = df["Squared Error"].rolling(window=30).mean()

    st.write(f"Based on {len(df)} markets with at least one trade.")

    col1, col2 = st.columns(2)
    col1.metric(label="Overall", value=f"{df['Squared Error'].mean():.3f}")
    col2.metric(
        label="Last 30 markets", value=f"{df['Squared Error'].tail(30).mean():.3f}"
    )

    st.altair_chart(
        alt.Chart(df)
        .mark_line(interpolate="basis")
        .encode(
            x="Date:T",
            y=alt.Y("Rolling Mean Squared Error:Q", scale=alt.Scale(domain=[0, 1])),
        )
        .interactive(),
        use_container_width=True,
    )


def monitor_market_outcome_bias(
    open_markets: t.Sequence[AgentMarket], resolved_markets: t.Sequence[AgentMarket]
) -> None:
    st.subheader("Market Outcome Bias")

    date_to_open_yes_proportion = {
        d: np.mean([int(m.current_p_yes > 0.5) for m in markets])
        for d, markets in groupby(
            open_markets,
            lambda x: check_not_none(x.created_time, "Only markets with created time can be used here.").date(),  # type: ignore # Bug, it says `Never has no attribute "date"  [attr-defined]` with Mypy, but in VSCode it works correctly.
        )
    }
    date_to_resolved_yes_proportion = {
        d: np.mean([int(m.boolean_outcome) for m in markets])
        for d, markets in groupby(
            resolved_markets,
            lambda x: check_not_none(x.created_time, "Only markets with created time can be used here.").date(),  # type: ignore # Bug, it says `Never has no attribute "date"  [attr-defined]` with Mypy, but in VSCode it works correctly.
        )
    }

    df_open = pd.DataFrame(
        date_to_open_yes_proportion.items(), columns=["date", "open_proportion"]
    )
    df_open["open_label"] = "Open's yes proportion"
    df_resolved = pd.DataFrame(
        date_to_resolved_yes_proportion.items(), columns=["date", "resolved_proportion"]
    )
    df_resolved["resolved_label"] = "Resolved's yes proportion"

    df = pd.merge(df_open, df_resolved, on="date")

    open_chart = (
        alt.Chart(df)
        .mark_line()
        .encode(x="date:T", y="open_proportion:Q", color="open_label:N")
    )

    resolved_chart = (
        alt.Chart(df)
        .mark_line()
        .encode(x="date:T", y="resolved_proportion:Q", color="resolved_label:N")
    )

    if len(df) > 0:
        st.altair_chart(
            alt.layer(open_chart, resolved_chart).interactive(),  # type: ignore # Doesn't expect `LayerChart`, but `Chart`, yet it works.
            use_container_width=True,
        )

    all_open_markets_yes_mean = np.mean(
        [int(m.current_p_yes > 0.5) for m in open_markets]
    )
    all_resolved_markets_yes_mean = np.mean(
        [
            (
                1
                if m.resolution == Resolution.YES
                else (
                    0
                    if m.resolution == Resolution.NO
                    else should_not_happen(f"Unexpected resolution: {m.resolution}")
                )
            )
            for m in resolved_markets
        ]
    )
    st.markdown(
        f"Mean proportion of 'YES' in open markets: {all_open_markets_yes_mean:.2f}"
        "\n\n"
        f"Mean proportion of 'YES' in resolved markets: {all_resolved_markets_yes_mean:.2f}"
    )
