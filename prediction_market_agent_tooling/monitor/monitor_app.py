import typing as t
from datetime import date, datetime, timedelta

import pytz
import streamlit as st

from prediction_market_agent_tooling.benchmark.utils import get_manifold_markets_dated
from prediction_market_agent_tooling.markets.markets import MarketType
from prediction_market_agent_tooling.monitor.markets.manifold import (
    DeployedManifoldAgent,
)
from prediction_market_agent_tooling.monitor.markets.omen import DeployedOmenAgent
from prediction_market_agent_tooling.monitor.monitor import (
    DeployedAgent,
    MonitorSettings,
    monitor_agent,
    monitor_market,
)
from prediction_market_agent_tooling.tools.utils import check_not_none

DEPLOYED_AGENT_TYPE_MAP: dict[MarketType, type[DeployedAgent]] = {
    MarketType.MANIFOLD: DeployedManifoldAgent,
    MarketType.OMEN: DeployedOmenAgent,
}


def get_deployed_agents(
    market_type: MarketType, settings: MonitorSettings, start_time: datetime
) -> list[DeployedAgent]:
    cls = DEPLOYED_AGENT_TYPE_MAP.get(market_type)
    if cls:
        return cls.from_monitor_settings(settings=settings, start_time=start_time)
    else:
        raise ValueError(f"Unknown market type: {market_type}")


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

    st.subheader("Market resolution")
    open_markets = get_manifold_markets_dated(oldest_date=start_time, filter_="open")
    resolved_markets = [
        m
        for m in get_manifold_markets_dated(oldest_date=start_time, filter_="resolved")
        if not m.has_unsuccessful_resolution
    ]
    monitor_market(open_markets=open_markets, resolved_markets=resolved_markets)

    with st.spinner("Loading agents..."):
        agents: list[DeployedAgent] = [
            agent
            for agent in get_deployed_agents(
                market_type=market_type, settings=settings, start_time=start_time
            )
        ]

    st.subheader("Agent bets")
    for agent in agents:
        with st.expander(f"Agent: '{agent.name}'"):
            monitor_agent(agent)
