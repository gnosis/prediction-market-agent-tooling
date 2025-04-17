from prediction_market_agent_tooling.deploy.agent_example import DeployableCoinFlipAgent
from prediction_market_agent_tooling.markets.markets import MarketType


def test_real_deployment_omen() -> None:
    DeployableCoinFlipAgent(enable_langfuse=False).deploy_local(
        sleep_time=0.001,
        market_type=MarketType.OMEN,
        run_time=100,
    )
    print("end")


def test_real_deployment() -> None:
    DeployableCoinFlipAgent(enable_langfuse=False).deploy_local(
        sleep_time=0.001,
        market_type=MarketType.SEER,
        run_time=100,
    )
    print("end")
