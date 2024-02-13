from datetime import datetime, timedelta
import pytz

from prediction_market_agent_tooling.markets.manifold import get_authenticated_user
from prediction_market_agent_tooling.monitor.markets.manifold import (
    DeployedManifoldAgent,
)
from prediction_market_agent_tooling.monitor.monitor import monitor_agent

if __name__ == "__main__":
    start_time = datetime.now() - timedelta(weeks=1)
    agent = DeployedManifoldAgent(
        name="foo",
        start_time=start_time.astimezone(pytz.UTC),
        manifold_user_id=get_authenticated_user().id,
    )
    monitor_agent(agent)
