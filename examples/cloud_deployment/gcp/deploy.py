import getpass
import json

import typer

from prediction_market_agent_tooling.deploy.agent_example import (
    DeployableAgent,
    DeployableAlwaysRaiseAgent,
    DeployableCoinFlipAgent,
)
from prediction_market_agent_tooling.markets.markets import MarketType
from prediction_market_agent_tooling.markets.omen.replicate.agent_example import (
    DeployableReplicateToOmenAgent,
)


def main(
    agent_name: str,
    cron_schedule: str = "0 */2 * * *",
    github_repo_url: str = "https://github.com/gnosis/prediction-market-agent-tooling",
    branch: str = "main",
    custom_gcp_fname: str | None = None,
    market_type: MarketType = MarketType.MANIFOLD,
    env_vars: str | None = None,
    secrets: str | None = None,
    timeout: int = 180,
) -> None:
    agent: DeployableAgent = {
        "coin_flip": DeployableCoinFlipAgent,
        "always_raise": DeployableAlwaysRaiseAgent,
        "replicate": DeployableReplicateToOmenAgent,
    }[agent_name]()
    agent.deploy_gcp(
        repository=f"git+{github_repo_url}.git@{branch}",
        market_type=market_type,
        labels={
            # Only lowercase letters, numbers, hyphens and underscores are allowed.
            "owner": getpass.getuser()
        },
        env_vars=json.loads(env_vars) if env_vars else None,
        # You can allow the cloud function to access secrets by adding the role: `gcloud projects add-iam-policy-binding ${GCP_PROJECT_ID} --member=serviceAccount:${GCP_SVC_ACC} --role=roles/container.admin`.
        # Must be in the format "env_var_in_container => secret_name:version", you can create secrets using `gcloud secrets create --labels owner=<your-name> <secret-name>` command.
        secrets=json.loads(secrets) if secrets else None,
        memory=512,
        cron_schedule=cron_schedule,
        gcp_fname=custom_gcp_fname,
        timeout=timeout,
    )


if __name__ == "__main__":
    typer.run(main)
