import typing as t
from datetime import datetime
from itertools import groupby

import altair as alt
import numpy as np
import pandas as pd
import streamlit as st
from pydantic import BaseModel
from pydantic_settings import BaseSettings, SettingsConfigDict

from prediction_market_agent_tooling.benchmark.utils import (
    CancelableMarketResolution,
    Market,
)
from prediction_market_agent_tooling.deploy.agent import MarketType, MonitorConfig
from prediction_market_agent_tooling.deploy.gcp.utils import list_gcp_functions
from prediction_market_agent_tooling.markets.data_models import ResolvedBet
from prediction_market_agent_tooling.tools.utils import should_not_happen


class MonitorSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env.monitor", env_file_encoding="utf-8", extra="ignore"
    )

    LOAD_FROM_GCP: bool = False
    MANIFOLD_API_KEYS: list[str] = []
    OMEN_PUBLIC_KEYS: t.Optional[str] = None
    PAST_N_WEEKS: int = 1

    @property
    def has_manual_agents(self) -> bool:
        return bool(self.MANIFOLD_API_KEYS or self.OMEN_PUBLIC_KEYS)


class DeployedAgent(BaseModel):
    name: str
    agent_class: str
    market_type: MarketType
    monitor_config: MonitorConfig

    raw_labels: dict[str, str] | None = None
    raw_env_vars: dict[str, str] | None = None

    @staticmethod
    def get_all_deployed_agents_gcp() -> t.Sequence["DeployedAgent"]:
        agents: list[DeployedAgent] = []

        for function in list_gcp_functions():
            agents.append(
                DeployedAgent(
                    name=function.name,
                    agent_class=function.labels["agent_class"],
                    market_type=MarketType(function.labels["market_type"]),
                    monitor_config=MonitorConfig.model_validate(
                        {
                            k.replace(MonitorConfig.LABEL_PREFIX, ""): v
                            for k, v in function.environment_variables.items()
                            if k.startswith(MonitorConfig.LABEL_PREFIX)
                        }
                    ),
                    raw_labels=dict(function.labels),
                    raw_env_vars=dict(function.service_config.environment_variables),
                )
            )

        return agents

    def get_resolved_bets(self) -> list[ResolvedBet]:
        raise NotImplementedError("Subclasses must implement this method.")

    @staticmethod
    def from_monitor_settings(
        settings: MonitorSettings, start_time: datetime
    ) -> list["DeployedAgent"]:
        raise NotImplementedError("Subclasses must implement this method.")


def monitor_agent(agent: DeployedAgent) -> None:
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
        "Profit": [bet.profit.amount for bet in agent_bets],
    }
    bets_df = pd.DataFrame(bets_info).sort_values(by="Resolved Time")

    # Metrics
    col1, col2 = st.columns(2)
    col1.metric(label="Number of bets", value=f"{len(agent_bets)}")
    col2.metric(label="% Correct", value=f"{100 * bets_df['Is Correct'].mean():.2f}%")

    # Chart of cumulative profit per day
    profit_info = {
        "Time": bets_df["Resolved Time"],
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
    st.subheader("Resolved Bet History")
    st.table(bets_df)


def monitor_market(open_markets: list[Market], resolved_markets: list[Market]) -> None:
    date_to_open_yes_proportion = {
        d: np.mean([int(m.p_yes > 0.5) for m in markets])
        for d, markets in groupby(open_markets, lambda x: x.created_time.date())
    }
    date_to_resolved_yes_proportion = {
        d: np.mean(
            [
                (
                    1
                    if m.resolution == CancelableMarketResolution.YES
                    else (
                        0
                        if m.resolution == CancelableMarketResolution.NO
                        else should_not_happen(f"Unexpected resolution: {m.resolution}")
                    )
                )
                for m in markets
            ]
        )
        for d, markets in groupby(resolved_markets, lambda x: x.created_time.date())
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

    st.altair_chart(
        alt.layer(open_chart, resolved_chart).interactive(),  # type: ignore # Doesn't expect `LayerChart`, but `Chart`, yet it works.
        use_container_width=True,
    )

    all_open_markets_yes_mean = np.mean([int(m.p_yes > 0.5) for m in open_markets])
    all_resolved_markets_yes_mean = np.mean(
        [
            (
                1
                if m.resolution == CancelableMarketResolution.YES
                else (
                    0
                    if m.resolution == CancelableMarketResolution.NO
                    else should_not_happen(f"Unexpected resolution: {m.resolution}")
                )
            )
            for m in resolved_markets
        ]
    )
    st.markdown(
        f"Total number of open markets {len(open_markets)} and resolved markets {len(resolved_markets)}"
        "\n\n"
        f"Mean proportion of 'YES' in open markets: {all_open_markets_yes_mean:.2f}"
        "\n\n"
        f"Mean proportion of 'YES' in resolved markets: {all_resolved_markets_yes_mean:.2f}"
    )
