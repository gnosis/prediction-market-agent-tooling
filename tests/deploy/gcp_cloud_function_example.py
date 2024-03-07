import functions_framework
from flask import Request

from prediction_market_agent_tooling.deploy.agent_example import DeployableCoinFlipAgent
from prediction_market_agent_tooling.markets.markets import MarketType


@functions_framework.http
def main(request: Request) -> str:
    DeployableCoinFlipAgent().run(market_type=MarketType.MANIFOLD, _place_bet=False)
    return "Success"
