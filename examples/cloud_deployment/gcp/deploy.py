import getpass
import typer

from prediction_market_agent_tooling.deploy.agent_example import (
    DeployableAgent,
    DeployableCoinFlipAgent,
    DeployableAlwaysRaiseAgent,
)
from prediction_market_agent_tooling.markets.markets import MarketType


def main(
    agent_name: str, cron_schedule: str = "0 */2 * * *", branch: str = "main"
) -> None:
    agent: DeployableAgent = {
        "coin_flip": DeployableCoinFlipAgent,
        "always_raise": DeployableAlwaysRaiseAgent,
    }[agent_name]()
    agent.deploy_gcp(
        # TODO: Switch to main.
        repository="git+https://github.com/gnosis/prediction-market-agent-tooling.git@{branch}",
        market_type=MarketType.MANIFOLD,
        labels={
            "owner": getpass.getuser()
        },  # Only lowercase letters, numbers, hyphens and underscores are allowed.
        env_vars={"EXAMPLE_ENV_VAR": "Gnosis"},
        # You can allow the cloud function to access secrets by adding the role: `gcloud projects add-iam-policy-binding ${GCP_PROJECT_ID} --member=serviceAccount:${GCP_SVC_ACC} --role=roles/container.admin`.
        secrets={
            "MANIFOLD_API_KEY": f"JUNG_PERSONAL_GMAIL_MANIFOLD_API_KEY:latest"
        },  # Must be in the format "env_var_in_container => secret_name:version", you can create secrets using `gcloud secrets create --labels owner=<your-name> <secret-name>` command.
        memory=256,
        cron_schedule=cron_schedule,
    )


if __name__ == "__main__":
    typer.run(main)
