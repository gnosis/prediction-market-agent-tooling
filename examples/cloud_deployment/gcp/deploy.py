import os

from prediction_market_agent_tooling.deploy.gcp.deploy import (
    deploy_to_gcp,
    remove_deployed_gcp_function,
    run_deployed_gcp_function,
    schedule_deployed_gcp_function,
)
from prediction_market_agent_tooling.deploy.gcp.utils import gcp_function_is_active
from prediction_market_agent_tooling.markets.markets import MarketType
from prediction_market_agent_tooling.config import APIKeys

if __name__ == "__main__":
    current_dir = os.path.dirname(os.path.realpath(__file__))
    fname = deploy_to_gcp(
        requirements_file=f"{current_dir}/../../../pyproject.toml",
        extra_deps=[
            "git+https://github.com/gnosis/prediction-market-agent-tooling.git"
        ],
        function_file=f"{current_dir}/agent.py",
        market_type=MarketType.MANIFOLD,
        api_keys={"MANIFOLD_API_KEY": APIKeys().manifold_api_key},
        memory=512,
    )

    # Check that the function is deployed
    assert gcp_function_is_active(fname)

    # Run the function
    response = run_deployed_gcp_function(fname)
    assert response.ok

    # Schedule the function to run once every 2 hours
    schedule_deployed_gcp_function(fname, cron_schedule="0 */2 * * *")

    # Delete the function
    remove_deployed_gcp_function(fname)
