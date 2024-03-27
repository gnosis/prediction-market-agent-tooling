import getpass
import json
import os

import typer

from prediction_market_agent_tooling.config import APIKeys
from prediction_market_agent_tooling.deploy.constants import OWNER_KEY
from prediction_market_agent_tooling.deploy.gcp.deploy import (
    deploy_to_gcp,
    run_deployed_gcp_function,
    schedule_deployed_gcp_function,
)
from prediction_market_agent_tooling.deploy.gcp.utils import gcp_function_is_active
from prediction_market_agent_tooling.gtypes import SecretStr, private_key_type
from prediction_market_agent_tooling.tools.utils import get_current_git_commit_sha


def main(
    fname: str = "remove-funds-from-omen-markets",
    github_repo_url: str = "https://github.com/gnosis/prediction-market-agent-tooling",
    from_private_key_secret_name: str = typer.Option(),
    openai_api_key_secret_name: str = typer.Option(),
    env_vars: str | None = None,
    secrets: str | None = None,
) -> None:
    """
    More manual example for cases where the default behavior falls short.
    """
    api_keys = APIKeys(
        # For GCP deployment, passwords, private keys, api keys, etc. must be stored in Secret Manager and here, only their name + version is passed.
        BET_FROM_PRIVATE_KEY=private_key_type(f"{from_private_key_secret_name}:latest"),
        OPENAI_API_KEY=SecretStr(f"{openai_api_key_secret_name}:latest"),
        # Not needed for replication, won't be saved in the deployment.
        MANIFOLD_API_KEY=None,
    )

    env_vars_parsed: dict[str, str] = (
        json.loads(env_vars) if env_vars else {}
    ) | api_keys.model_dump_public()
    secrets_parsed: dict[str, str] = (
        json.loads(secrets) if secrets else {}
    ) | api_keys.model_dump_secrets()

    current_dir = os.path.dirname(os.path.abspath(__file__))
    deploy_to_gcp(
        gcp_fname=fname,
        requirements_file=None,
        extra_deps=[
            f"git+{github_repo_url}.git@{get_current_git_commit_sha()}#egg=prediction-market-agent-tooling[langchain]",
        ],
        function_file=os.path.join(current_dir, "remove_funds_agent_example.py"),
        memory=512,
        entrypoint_function_name="main",
        timeout=540,
        labels={OWNER_KEY: getpass.getuser()},
        env_vars=env_vars_parsed,
        secrets=secrets_parsed,
    )

    # Check that the function is deployed
    if not gcp_function_is_active(fname):
        raise RuntimeError("Failed to deploy the function")

    # Run the function
    response = run_deployed_gcp_function(fname)
    if not response.ok:
        raise RuntimeError("Failed to run the deployed function")

    # Schedule the function
    schedule_deployed_gcp_function(fname, cron_schedule="0 8 * * *")


if __name__ == "__main__":
    typer.run(main)
