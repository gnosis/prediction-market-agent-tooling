from web3 import Web3

from prediction_market_agent_tooling.config import APIKeys
from prediction_market_agent_tooling.gtypes import OutcomeStr, xDai, OutcomeWei
from prediction_market_agent_tooling.markets.seer.data_models import RedeemParams
from prediction_market_agent_tooling.markets.seer.seer_contracts import (
    SeerMarketFactory,
    GnosisRouter,
)
from prediction_market_agent_tooling.markets.seer.subgraph_data_models import (
    CreateCategoricalMarketsParams,
)
from prediction_market_agent_tooling.tools.datetime_utc import DatetimeUTC


def build_params() -> CreateCategoricalMarketsParams:
    return SeerMarketFactory.build_market_params(
        market_question="test test test",
        outcomes=[OutcomeStr("Yes"), OutcomeStr("No")],
        opening_time=DatetimeUTC.now(),
        language="en_US",
        category="misc",
        min_bond=xDai(0.01),
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


def test_redeem_base(local_web3: Web3, test_keys: APIKeys) -> None:
    # We don't care if the transaction has the expected effect (would require lots of mocking).
    # We just care about parameter serialization.

    params = RedeemParams(
        market=Web3.to_checksum_address(
            "0xa4b71ac2d0e17e1242e2d825e621acd18f0054ea"
        ),  # example closed YES/NO market
        outcomeIndexes=[0, 1, 2],
        amounts=[OutcomeWei(int(1e18)), OutcomeWei(int(1e18)), OutcomeWei(int(1e18))],
    )
    GnosisRouter().redeem_to_base(test_keys, params=params, web3=local_web3)
