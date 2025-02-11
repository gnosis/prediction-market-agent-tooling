from prediction_market_agent_tooling.deploy.agent_example import DeployableCoinFlipAgent
from prediction_market_agent_tooling.markets.markets import MarketType

if __name__ == "__main__":
    agent = DeployableCoinFlipAgent()
    agent.run(market_type=MarketType.SEER)
    print("done")
