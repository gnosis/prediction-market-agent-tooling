import getpass

import typer
from pydantic.types import SecretStr
from web3 import Web3

from prediction_market_agent_tooling.config import APIKeys
from prediction_market_agent_tooling.deploy.agent_example import (
    DeployableAgent,
    DeployableAlwaysRaiseAgent,
    DeployableCoinFlipAgent,
)
from prediction_market_agent_tooling.gtypes import PrivateKey
from prediction_market_agent_tooling.markets.markets import MarketType


def main(
    agent_name: str,
    cron_schedule: str = "0 */2 * * *",
    github_repo_url: str = "https://github.com/gnosis/prediction-market-agent-tooling",
    branch: str = "main",
    custom_gcp_fname: str | None = None,
    market_type: MarketType = MarketType.MANIFOLD,
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
        api_keys=APIKeys(
            BET_FROM_ADDRESS=Web3.to_checksum_address(
                "0x3666DA333dAdD05083FEf9FF6dDEe588d26E4307"
            ),
            # For GCP deployment, passwords, private keys, api keys, etc. must be stored in Secret Manager and here, only their name + version is passed.
            MANIFOLD_API_KEY=SecretStr("JUNG_PERSONAL_GMAIL_MANIFOLD_API_KEY:latest"),
            BET_FROM_PRIVATE_KEY=PrivateKey(
                "0x3666DA333dAdD05083FEf9FF6dDEe588d26E4307:latest"
            ),
        ),
        memory=256,
        cron_schedule=cron_schedule,
        gcp_fname=custom_gcp_fname,
    )


if __name__ == "__main__":
    typer.run(main)
