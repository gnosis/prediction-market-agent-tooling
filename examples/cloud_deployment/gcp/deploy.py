import os
import getpass

from prediction_market_agent_tooling.config import APIKeys
from prediction_market_agent_tooling.deploy.gcp.deploy import (
    deploy_to_gcp,
    remove_deployed_gcp_function,
    run_deployed_gcp_function,
    schedule_deployed_gcp_function,
)
from prediction_market_agent_tooling.deploy.gcp.utils import gcp_function_is_active
from prediction_market_agent_tooling.markets.markets import MarketType

if __name__ == "__main__":
    current_dir = os.path.dirname(os.path.realpath(__file__))
    fname = deploy_to_gcp(
        requirements_file=None,
        extra_deps=[
            "git+https://github.com/gnosis/prediction-market-agent-tooling.git@main"
        ],
        function_file=f"{current_dir}/agent.py",
        market_type=MarketType.MANIFOLD,
        labels={
            "owner": getpass.getuser()
        },  # Only lowercase letters, numbers, hyphens and underscores are allowed.
        env_vars={"EXAMPLE_ENV_VAR": "Gnosis"},
        # You can allow the cloud function to access secrets by adding the role: `gcloud projects add-iam-policy-binding ${GCP_PROJECT_ID} --member=serviceAccount:${GCP_SVC_ACC} --role=roles/container.admin`.
        secrets={
            "MANIFOLD_API_KEY": f"JUNG_PERSONAL_GMAIL_MANIFOLD_API_KEY:latest"
        },  # Must be in the format "env_var_in_container => secret_name:version", you can create secrets using `gcloud secrets create --labels owner=<your-name> <secret-name>` command.
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
