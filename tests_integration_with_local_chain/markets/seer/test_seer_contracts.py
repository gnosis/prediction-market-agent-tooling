import datetime

from web3 import Web3

from prediction_market_agent_tooling.config import APIKeys
from prediction_market_agent_tooling.markets.seer.data_models import (
    CreateCategoricalMarketsParams,
)
from prediction_market_agent_tooling.markets.seer.seer_contracts import MarketFactory


def build_params() -> CreateCategoricalMarketsParams:
    opening_time = int(
        (datetime.datetime.utcnow() + datetime.timedelta(days=1)).timestamp()
    )
    return CreateCategoricalMarketsParams(
        token_names=["YES", "NO"],
        min_bond=str(int(1e18)),
        openingTime=opening_time,
        outcomes=["Yes", "No"],
        market_name="test test test",
    )


def test_create_market(local_web3: Web3, test_keys: APIKeys) -> None:
    factory = MarketFactory()
    num_initial_markets = factory.market_count(web3=local_web3)
    params = build_params()
    tx_receipt = factory.create_categorical_market(
        api_keys=test_keys, params=params, web3=local_web3
    )

    num_final_markets = factory.market_count(web3=local_web3)
    assert num_initial_markets + 1 == num_final_markets
