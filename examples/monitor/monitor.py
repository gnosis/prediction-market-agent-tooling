from datetime import datetime, timedelta
from prediction_market_agent_tooling.markets.manifold import get_authenticated_user
from prediction_market_agent_tooling.monitor.monitor import (
    DeployedManifoldAgent,
    monitor_agent,
)


agent = DeployedManifoldAgent(
    name="foo",
    start_time=datetime.now() - timedelta(weeks=2),
    manifold_user=get_authenticated_user(),
)

monitor_agent(agent)
