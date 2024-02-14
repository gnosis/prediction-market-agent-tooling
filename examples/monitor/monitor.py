from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
import streamlit as st

from prediction_market_agent_tooling.markets.manifold import get_authenticated_user
from prediction_market_agent_tooling.monitor.markets.manifold import (
    DeployedManifoldAgent,
)
from prediction_market_agent_tooling.monitor.monitor import monitor_agent

if __name__ == "__main__":
    start_time = datetime.now() - timedelta(weeks=1)
    agent = DeployedManifoldAgent(
        name="foo",
        start_time=start_time.astimezone(ZoneInfo("UTC")),
        manifold_user_id=get_authenticated_user().id,
    )
    st.set_page_config(layout="wide")  # Best viewed with a wide screen
    st.title(f"Monitoring Agent: '{agent.name}'")
    monitor_agent(agent)
