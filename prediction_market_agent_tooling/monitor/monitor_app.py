import typing as t
from datetime import date, datetime, timedelta

import pytz
import streamlit as st

from prediction_market_agent_tooling.benchmark.utils import (
    Market,
    get_manifold_markets_dated,
)
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
    market_type: MarketType,
    start_time: datetime,
    settings: MonitorSettings,
) -> list[DeployedAgent]:
    cls = DEPLOYED_AGENT_TYPE_MAP.get(market_type)
    if cls is None:
        raise ValueError(f"Unknown market type: {market_type}")

    agents: list[DeployedAgent] = []

    if settings.LOAD_FROM_GCP:
        agents.extend(cls.get_all_deployed_agents_gcp())

    agents.extend(cls.from_monitor_settings(settings=settings, start_time=start_time))

    return agents


def get_open_and_resolved_markets(
    start_time: datetime,
    market_type: MarketType,
) -> tuple[list[Market], list[Market]]:
    open_markets: list[Market]
    resolved_markets: list[Market]

    if market_type == MarketType.MANIFOLD:
        open_markets = get_manifold_markets_dated(
            oldest_date=start_time, filter_="open"
        )
        resolved_markets = [
            m
            for m in get_manifold_markets_dated(
                oldest_date=start_time, filter_="resolved"
            )
            if not m.has_unsuccessful_resolution
        ]

    elif market_type == MarketType.OMEN:
        # TODO: Add Omen market support: https://github.com/gnosis/prediction-market-agent-tooling/issues/56
        open_markets = []
        resolved_markets = []

    else:
        raise ValueError(f"Unknown market type: {market_type}")

    return open_markets, resolved_markets


def monitor_app() -> None:
    settings = MonitorSettings()
    market_type: MarketType = check_not_none(
        st.selectbox(label="Market type", options=list(MarketType), index=0)
    )
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

    with st.spinner("Loading agents"):
        agents: list[DeployedAgent] = get_deployed_agents(
            market_type=market_type,
            start_time=start_time,
            settings=settings,
        )

    oldest_start_time = min(agent.monitor_config.start_time for agent in agents)

    st.subheader("Market resolution")

    with st.spinner("Loading markets"):
        open_markets, resolved_markets = get_open_and_resolved_markets(
            start_time=oldest_start_time, market_type=market_type
        )
    (
        monitor_market(open_markets=open_markets, resolved_markets=resolved_markets)
        if open_markets and resolved_markets
        else st.warning("No market data found.")
    )

    st.subheader("Agent bets")
    for agent in agents:
        with st.expander(f"Agent: '{agent.name}'"):
            monitor_agent(agent)
