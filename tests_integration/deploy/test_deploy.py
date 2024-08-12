from web3 import Web3

from prediction_market_agent_tooling.deploy.agent_example import DeployableCoinFlipAgent
from prediction_market_agent_tooling.markets.markets import MarketType


# Note that this test can trigger redeeming of funds, which costs money to run.
def test_local_deployment(local_web3: Web3) -> None:
    DeployableCoinFlipAgent(place_bet=False).deploy_local(
        sleep_time=0.001,
        market_type=MarketType.OMEN,
        timeout=0.01,
    )
