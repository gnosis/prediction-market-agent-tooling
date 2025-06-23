import typer
from web3 import Web3

from prediction_market_agent_tooling.markets.omen.omen_contracts import (
    OmenAgentResultMappingContract,
    SeerAgentResultMappingContract,
)

APP = typer.Typer()


@APP.command()
def seer(market_id: str) -> None:
    for prediction in SeerAgentResultMappingContract().get_predictions(
        Web3.to_checksum_address(market_id)
    ):
        print(prediction)


@APP.command()
def omen(market_id: str) -> None:
    for prediction in OmenAgentResultMappingContract().get_predictions(
        Web3.to_checksum_address(market_id)
    ):
        print(prediction)


if __name__ == "__main__":
    APP()
