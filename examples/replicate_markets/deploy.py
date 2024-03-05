import os

from prediction_market_agent_tooling.deploy.gcp.deploy import (
    deploy_to_gcp,
    run_deployed_gcp_function,
    schedule_deployed_gcp_function,
)
from prediction_market_agent_tooling.deploy.gcp.utils import gcp_function_is_active

fname = "replicate_markets"
current_dir = os.path.dirname(os.path.abspath(__file__))
deploy_to_gcp(
    gcp_fname=fname,
    requirements_file=None,
    extra_deps=[
        "git+https://github.com/gnosis/prediction-market-agent-tooling.git@449c67df2ec02f61411e153565c5e3f8ba01dda1",
        "langchain",
        "langchain_openai",
    ],
    function_file=os.path.join(current_dir, "agent_example.py"),
    memory=512,
    entrypoint_function_name="main",
    timeout=180,
    labels=None,
    env_vars=None,  # TODO add env vars
    secrets=None,  # TODO add secrets
)

# Check that the function is deployed
if not gcp_function_is_active(fname):
    raise RuntimeError("Failed to deploy the function")

# Run the function
response = run_deployed_gcp_function(fname)
if not response.ok:
    raise RuntimeError("Failed to run the deployed function")

# Schedule the function
schedule_deployed_gcp_function(fname, cron_schedule="0 */6 * * *")
