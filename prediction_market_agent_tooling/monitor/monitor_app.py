import typing as t
from datetime import date, datetime, timedelta

import pytz
import streamlit as st

from prediction_market_agent_tooling.markets.agent_market import (
    AgentMarket,
    FilterBy,
    SortBy,
)
from prediction_market_agent_tooling.markets.markets import MarketType
from prediction_market_agent_tooling.monitor.markets.manifold import (
    DeployedManifoldAgent,
)
from prediction_market_agent_tooling.monitor.markets.omen import DeployedOmenAgent
from prediction_market_agent_tooling.monitor.markets.polymarket import (
    DeployedPolymarketAgent,
)
from prediction_market_agent_tooling.monitor.monitor import (
    DeployedAgent,
    MonitorSettings,
    monitor_agent,
    monitor_market,
)
from prediction_market_agent_tooling.tools.utils import (
    DatetimeWithTimezone,
    add_utc_timezone_validator,
    check_not_none,
    utcnow,
)

MAX_MONITOR_MARKETS = 1000

MARKET_TYPE_TO_DEPLOYED_AGENT: dict[MarketType, type[DeployedAgent]] = {
    MarketType.MANIFOLD: DeployedManifoldAgent,
    MarketType.OMEN: DeployedOmenAgent,
    MarketType.POLYMARKET: DeployedPolymarketAgent,
}


def get_deployed_agents(
    market_type: MarketType,
    settings: MonitorSettings,
    start_time: DatetimeWithTimezone | None,
) -> list[DeployedAgent]:
    cls = MARKET_TYPE_TO_DEPLOYED_AGENT.get(market_type)
    if cls is None:
        raise ValueError(f"Unknown market type: {market_type}")

    agents: list[DeployedAgent] = []

    if settings.LOAD_FROM_GCF:
        agents.extend(cls.from_all_gcp_functions())

    if settings.LOAD_FROM_GCK:
        agents.extend(cls.from_all_gcp_cronjobs())

    agents.extend(
        cls.from_monitor_settings(settings=settings, start_time=start_time or utcnow())
    )

    return agents


def get_open_and_resolved_markets(
    start_time: datetime,
    market_type: MarketType,
) -> tuple[t.Sequence[AgentMarket], t.Sequence[AgentMarket]]:
    cls = market_type.market_class
    open_markets = cls.get_binary_markets(
        limit=MAX_MONITOR_MARKETS,
        sort_by=SortBy.NEWEST,
        created_after=start_time,
        filter_by=FilterBy.OPEN,
    )
    resolved_markets = cls.get_binary_markets(
        limit=MAX_MONITOR_MARKETS,
        sort_by=SortBy.NEWEST,
        created_after=start_time,
        filter_by=FilterBy.RESOLVED,
    )
    resolved_markets = [m for m in resolved_markets if m.has_successful_resolution()]
    return open_markets, resolved_markets


def monitor_app(
    enabled_market_types: list[MarketType],
) -> None:
    settings = MonitorSettings()
    market_type: MarketType = check_not_none(
        st.selectbox(label="Market type", options=enabled_market_types, index=0)
    )
    start_time: DatetimeWithTimezone | None = (
        add_utc_timezone_validator(
            datetime.combine(
                t.cast(
                    # This will be always a date for us, so casting.
                    date,
                    st.date_input(
                        "Start time",
                        value=utcnow() - timedelta(weeks=settings.PAST_N_WEEKS),
                    ),
                ),
                datetime.min.time(),
            )
        )
        if settings.has_manual_agents
        else None
    )

    with st.spinner("Loading agents"):
        agents: list[DeployedAgent] = get_deployed_agents(
            market_type=market_type,
            settings=settings,
            start_time=start_time,
        )

    oldest_start_time = (
        min(agent.start_time for agent in agents)
        if agents
        else datetime(2020, 1, 1, tzinfo=pytz.UTC)
    )

    st.header("Market Info")
    with st.spinner("Loading markets"):
        open_markets, resolved_markets = get_open_and_resolved_markets(
            start_time=oldest_start_time, market_type=market_type
        )
    (
        monitor_market(open_markets=open_markets, resolved_markets=resolved_markets)
        if open_markets and resolved_markets
        else st.warning("No market data found.")
    )

    st.header("Agent Info")
    for agent in agents:
        with st.expander(f"Agent: '{agent.name}'"):
            monitor_agent(agent)
