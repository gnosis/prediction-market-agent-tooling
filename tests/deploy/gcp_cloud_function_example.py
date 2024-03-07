import functions_framework
from flask import Request

from prediction_market_agent_tooling.deploy.agent_example import DeployableCoinFlipAgent


@functions_framework.http
def main(request: Request) -> str:
    DeployableCoinFlipAgent().run()
    return "Success"
