import typer
from loguru import logger

from prediction_market_agent_tooling.deploy.gcp.deploy import (
    remove_deployed_gcp_function,
)


def main(names: list[str]) -> None:
    for name in names:
        logger.info(f"Removing {name}.")
        remove_deployed_gcp_function(name)


if __name__ == "__main__":
    typer.run(main)
