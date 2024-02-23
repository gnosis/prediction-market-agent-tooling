import typing as t
from datetime import date, datetime, timedelta

import pytz
import streamlit as st
from pydantic_settings import BaseSettings, SettingsConfigDict

from prediction_market_agent_tooling.benchmark.utils import get_manifold_markets_dated
from prediction_market_agent_tooling.markets.manifold.api import get_authenticated_user
from prediction_market_agent_tooling.markets.markets import MarketType
from prediction_market_agent_tooling.monitor.markets.manifold import (
    DeployedManifoldAgent,
)
from prediction_market_agent_tooling.monitor.monitor import (
    monitor_agent,
    monitor_market,
)
from prediction_market_agent_tooling.tools.utils import check_not_none


class MonitorSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env.monitor", env_file_encoding="utf-8", extra="ignore"
    )

    MANIFOLD_API_KEYS: list[str] = []
    PAST_N_WEEKS: int = 1


def monitor_app() -> None:
    settings = MonitorSettings()
    start_time = datetime.combine(
        t.cast(
            # This will be always a date for us, so casting.
            date,
            st.date_input(
                "Start time",
                value=datetime.now() - timedelta(weeks=settings.PAST_N_WEEKS),
            ),
        ),
        datetime.min.time(),
    ).replace(tzinfo=pytz.UTC)
    market_type: MarketType = check_not_none(
        st.selectbox(label="Market type", options=list(MarketType), index=0)
    )

    if market_type != MarketType.MANIFOLD:
        st.warning("Only Manifold markets are supported for now.")
        return

    st.subheader("Market resolution")
    open_markets = get_manifold_markets_dated(oldest_date=start_time, filter_="open")
    resolved_markets = [
        m
        for m in get_manifold_markets_dated(oldest_date=start_time, filter_="resolved")
        if m.has_successful_resolution
    ]
    monitor_market(open_markets=open_markets, resolved_markets=resolved_markets)

    with st.spinner("Loading Manifold agents..."):
        agents: list[DeployedManifoldAgent] = []
        for key in settings.MANIFOLD_API_KEYS:
            manifold_user = get_authenticated_user(key)
            agents.append(
                DeployedManifoldAgent(
                    name=manifold_user.name,
                    manifold_user_id=manifold_user.id,
                    start_time=start_time,
                )
            )

    st.subheader("Agent bets")
    for agent in agents:
        with st.expander(f"Agent: '{agent.name}'"):
            monitor_agent(agent)
