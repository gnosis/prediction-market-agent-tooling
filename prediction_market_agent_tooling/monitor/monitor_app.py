import streamlit as st
from pydantic_settings import BaseSettings, SettingsConfigDict

from prediction_market_agent_tooling.benchmark.utils import get_manifold_markets_dated
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
    MonitorSettings()
    market_type: MarketType = check_not_none(
        st.selectbox(label="Market type", options=list(MarketType), index=0)
    )

    if market_type != MarketType.MANIFOLD:
        st.warning("Only Manifold markets are supported for now.")
        return

    with st.spinner("Loading agents..."):
        agents = DeployedManifoldAgent.get_all_deployed_agents_gcp()

    oldest_start_time = min(agent.monitor_config.start_time for agent in agents)

    st.subheader("Market resolution")
    open_markets = get_manifold_markets_dated(
        oldest_date=oldest_start_time, filter_="open"
    )
    resolved_markets = [
        m
        for m in get_manifold_markets_dated(
            oldest_date=oldest_start_time, filter_="resolved"
        )
        if not m.has_unsuccessful_resolution
    ]
    monitor_market(open_markets=open_markets, resolved_markets=resolved_markets)

    st.subheader("Agent bets")
    for agent in agents:
        with st.expander(f"Agent: '{agent.name}'"):
            monitor_agent(agent)
