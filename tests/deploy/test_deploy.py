import os
import time

from prediction_market_agent_tooling.deploy.agent_example import DeployableCoinFlipAgent
from prediction_market_agent_tooling.deploy.gcp.deploy import (
    deploy_to_gcp,
    remove_deployed_gcp_function,
    schedule_deployed_gcp_function,
)
from prediction_market_agent_tooling.deploy.gcp.utils import gcp_function_is_active
from prediction_market_agent_tooling.markets.markets import MarketType
from prediction_market_agent_tooling.monitor.markets.manifold import (
    DeployedManifoldAgent,
)
from prediction_market_agent_tooling.monitor.monitor import monitor_agent
from prediction_market_agent_tooling.tools.utils import (
    get_current_git_commit_sha,
    get_current_git_url,
)


def test_local_deployment() -> None:
    DeployableCoinFlipAgent().deploy_local(
        sleep_time=0.001,
        market_type=MarketType.MANIFOLD,
        timeout=0.01,
        place_bet=False,
    )


def test_gcp_deployment() -> None:
    gcp_fname = f"coin-flip-{int(time.time())}"
    env_vars = {
        "name": "coin-flip",
        "deployableagent_class_name": "DeployableCoinFlipAgent",
        "start_time": "2021-01-01T00:00:00Z",
        "manifold_user_id": "foo",
    }
    prefixed_env_vars = {
        f"{DeployedManifoldAgent.PREFIX}{k}": v for k, v in env_vars.items()
    }

    try:
        deploy_to_gcp(
            gcp_fname=gcp_fname,
            requirements_file=None,
            extra_deps=[
                f"git+{get_current_git_url()}@{get_current_git_commit_sha()}",
            ],
            function_file=os.path.join(
                os.path.dirname(os.path.abspath(__file__)),
                "gcp_cloud_function_example.py",
            ),
            memory=512,
            entrypoint_function_name="main",
            timeout=180,
            labels=None,
            env_vars=prefixed_env_vars,
            secrets=None,
        )

        assert gcp_function_is_active(gcp_fname)
        schedule_deployed_gcp_function(gcp_fname, cron_schedule="0 8 * * *")

        deployed_agent = DeployedManifoldAgent.from_gcp_function_name(gcp_fname)
        monitor_agent(deployed_agent)

    finally:
        remove_deployed_gcp_function(gcp_fname)
