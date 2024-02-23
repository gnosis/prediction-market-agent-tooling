import getpass

import typer

from prediction_market_agent_tooling.deploy.agent_example import (
    DeployableAgent,
    DeployableAlwaysRaiseAgent,
    DeployableCoinFlipAgent,
)
from prediction_market_agent_tooling.markets.markets import MarketType


def main(
    agent_name: str,
    cron_schedule: str = "0 */2 * * *",
    github_repo_url: str = "https://github.com/gnosis/prediction-market-agent-tooling",
    branch: str = "main",
    custom_gcp_fname: str | None = None,
    market_type: MarketType = MarketType.OMEN,
) -> None:
    agent: DeployableAgent = {
        "coin_flip": DeployableCoinFlipAgent,
        "always_raise": DeployableAlwaysRaiseAgent,
    }[agent_name]()
    agent.deploy_gcp(
        repository=f"git+{github_repo_url}.git@{branch}",
        market_type=market_type,
        labels={
            "owner": getpass.getuser()
        },  # Only lowercase letters, numbers, hyphens and underscores are allowed.
        env_vars={"BET_FROM_ADDRESS": "0x3666DA333dAdD05083FEf9FF6dDEe588d26E4307"},
        # You can allow the cloud function to access secrets by adding the role: `gcloud projects add-iam-policy-binding ${GCP_PROJECT_ID} --member=serviceAccount:${GCP_SVC_ACC} --role=roles/container.admin`.
        secrets={
            "MANIFOLD_API_KEY": "JUNG_PERSONAL_GMAIL_MANIFOLD_API_KEY:latest",
            "BET_FROM_PRIVATE_KEY": "0x3666DA333dAdD05083FEf9FF6dDEe588d26E4307:latest",
        },  # Must be in the format "env_var_in_container => secret_name:version", you can create secrets using `gcloud secrets create --labels owner=<your-name> <secret-name>` command.
        memory=256,
        cron_schedule=cron_schedule,
        gcp_fname=custom_gcp_fname,
    )


if __name__ == "__main__":
    typer.run(main)
