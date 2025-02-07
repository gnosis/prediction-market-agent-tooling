from web3 import Web3

from prediction_market_agent_tooling.config import APIKeys
from prediction_market_agent_tooling.gtypes import xDai, xdai_type
from prediction_market_agent_tooling.markets.seer.data_models import (
    CreateCategoricalMarketsParams,
)
from prediction_market_agent_tooling.markets.seer.seer_contracts import (
    SeerMarketFactory,
)
from prediction_market_agent_tooling.tools.datetime_utc import DatetimeUTC


def build_params() -> CreateCategoricalMarketsParams:
    return SeerMarketFactory.build_market_params(
        market_question="test test test",
        outcomes=["Yes", "No"],
        opening_time=DatetimeUTC.now(),
        language="en_US",
        category="misc",
        min_bond_xdai=xdai_type(xDai(0.01)),
    )


def test_create_market(local_web3: Web3, test_keys: APIKeys) -> None:
    factory = SeerMarketFactory()
    num_initial_markets = factory.market_count(web3=local_web3)
    params = build_params()
    factory.create_categorical_market(
        api_keys=test_keys, params=params, web3=local_web3
    )

    num_final_markets = factory.market_count(web3=local_web3)
    assert num_initial_markets + 1 == num_final_markets
