import getpass
import json
from enum import Enum

import typer
from pydantic.types import SecretStr
from web3 import Web3

from prediction_market_agent_tooling.config import APIKeys
from prediction_market_agent_tooling.deploy.agent_example import (
    DeployableAgent,
    DeployableAlwaysRaiseAgent,
    DeployableCoinFlipAgent,
)
from prediction_market_agent_tooling.gtypes import private_key_type
from prediction_market_agent_tooling.markets.markets import MarketType
from prediction_market_agent_tooling.markets.omen.replicate.agent_example import (
    DeployableReplicateToOmenAgent,
)


class AgentName(str, Enum):
    coin_flip = "coin_flip"
    always_raise = "always_raise"
    replicate = "replicate"


def main(
    agent_name: AgentName,
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
        AgentName.coin_flip: DeployableCoinFlipAgent,
        AgentName.always_raise: DeployableAlwaysRaiseAgent,
        AgentName.replicate: DeployableReplicateToOmenAgent,
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
        api_keys=APIKeys(
            BET_FROM_ADDRESS=Web3.to_checksum_address(
                "0x3666DA333dAdD05083FEf9FF6dDEe588d26E4307"
            ),
            # For GCP deployment, passwords, private keys, api keys, etc. must be stored in Secret Manager and here, only their name + version is passed.
            MANIFOLD_API_KEY=SecretStr("JUNG_PERSONAL_GMAIL_MANIFOLD_API_KEY:latest"),
            BET_FROM_PRIVATE_KEY=private_key_type(
                "0x3666DA333dAdD05083FEf9FF6dDEe588d26E4307:latest"
            ),
        ),
        cron_schedule=cron_schedule,
        gcp_fname=custom_gcp_fname,
        timeout=timeout,
        dump_monitor_agent=agent_name != AgentName.replicate,
    )


if __name__ == "__main__":
    typer.run(main)
