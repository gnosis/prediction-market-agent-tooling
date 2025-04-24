from unittest.mock import patch

from web3 import Web3

from prediction_market_agent_tooling.deploy.agent_example import DeployableCoinFlipAgent
from prediction_market_agent_tooling.markets.markets import MarketType
from prediction_market_agent_tooling.tools.contract import ContractBaseClass


def test_local_deployment(local_web3: Web3) -> None:
    with patch.object(ContractBaseClass, "get_web3", return_value=local_web3):
        DeployableCoinFlipAgent(enable_langfuse=False).deploy_local(
            sleep_time=0.001,
            market_type=MarketType.SEER_MULTI,
            run_time=0.01,
        )
