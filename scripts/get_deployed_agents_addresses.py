from datetime import datetime

import typer
from google.cloud.functions_v2 import FunctionServiceClient

from prediction_market_agent_tooling.gtypes import private_key_type, xdai_type
from prediction_market_agent_tooling.markets.markets import MarketType
from prediction_market_agent_tooling.markets.omen.data_models import (
    OMEN_FALSE_OUTCOME,
    OMEN_TRUE_OUTCOME,
)
from prediction_market_agent_tooling.markets.omen.omen import (
    OMEN_DEFAULT_MARKET_FEE,
    omen_create_market_tx,
)
from prediction_market_agent_tooling.monitor.monitor import MonitorSettings
from prediction_market_agent_tooling.monitor.monitor_app import get_deployed_agents
from prediction_market_agent_tooling.tools.web3_utils import verify_address


def main() -> None:
    # get deployed agents
    settings = MonitorSettings()
    settings.LOAD_FROM_GCP = True
    # client = FunctionServiceClient()
    # functions = list(client.list_functions(parent=get_gcloud_parent()))
    t = get_deployed_agents(
        market_type=MarketType.OMEN, settings=settings, start_time=None
    )
    for agent in t:
        print(f"public key {agent.omen_public_key}")
    print(t)


if __name__ == "__main__":
    main()
