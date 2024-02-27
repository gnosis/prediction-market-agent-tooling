import typing as t
from datetime import date, datetime, timedelta

import pytz
import streamlit as st

from prediction_market_agent_tooling.markets.agent_market import (
    AgentMarket,
    FilterBy,
    SortBy,
)
from prediction_market_agent_tooling.markets.markets import MARKET_TYPE_MAP, MarketType
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

MAX_MONITOR_MARKETS = 1000

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


def get_open_and_resolved_markets(
    start_time: datetime,
    market_type: MarketType,
) -> tuple[list[AgentMarket], list[AgentMarket]]:
    cls = MARKET_TYPE_MAP.get(market_type)
    if market_type is None:
        raise ValueError(f"Unknown market type: {market_type}")

    open_markets = cls.get_binary_markets(
        limit=MAX_MONITOR_MARKETS,
        sort_by=SortBy.NEWEST,
        created_after=start_time,
        filter_by=FilterBy.OPEN,
    )
    closed_markets = cls.get_binary_markets(
        limit=MAX_MONITOR_MARKETS,
        sort_by=SortBy.NEWEST,
        created_after=start_time,
        filter_by=FilterBy.CLOSED,
    )
    resolved_markets = [
        m for m in closed_markets if m.is_resolved() and m.has_successful_resolution()
    ]

    return open_markets, resolved_markets


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
    open_markets, resolved_markets = get_open_and_resolved_markets(
        start_time, market_type
    )
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
