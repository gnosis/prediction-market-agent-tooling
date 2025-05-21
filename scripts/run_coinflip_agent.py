from prediction_market_agent_tooling.deploy.agent_example import (
    DeployableCoinFlipAgent,
    MarketType,
)


def main() -> None:
    DeployableCoinFlipAgent().run(MarketType.OMEN)


if __name__ == "__main__":
    main()
