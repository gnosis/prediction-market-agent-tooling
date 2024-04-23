from prediction_market_agent_tooling.deploy.agent_example import DeployableCoinFlipAgent
from prediction_market_agent_tooling.markets.markets import MarketType


def test_local_deployment() -> None:
    DeployableCoinFlipAgent().deploy_local(
        sleep_time=0.001,
        market_type=MarketType.OMEN,
        timeout=0.01,
        place_bet=False,
    )
