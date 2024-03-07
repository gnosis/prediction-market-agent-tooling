import typer

from prediction_market_agent_tooling.deploy.gcp.deploy import run_deployed_gcp_function


def main(names: list[str]) -> None:
    for name in names:
        print(f"Running {name}.")
        run_deployed_gcp_function(name)


if __name__ == "__main__":
    typer.run(main)
