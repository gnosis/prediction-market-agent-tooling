from web3 import Web3

from prediction_market_agent_tooling.config import APIKeys
from prediction_market_agent_tooling.gtypes import OutcomeStr, xDai
from prediction_market_agent_tooling.markets.seer.seer_contracts import (
    SeerMarketFactory,
)
from prediction_market_agent_tooling.markets.seer.subgraph_data_models import (
    CreateCategoricalMarketsParams,
)
from prediction_market_agent_tooling.tools.contract import (
    ContractWrapped1155BaseClass,
    ContractWrapped1155OnGnosisChain,
    init_collateral_token_contract,
    to_gnosis_chain_contract,
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


def test_wrapped_erc1155_init_collateral(local_web3: Web3) -> None:
    outcome_token_contract = Web3.to_checksum_address(
        "0x924ba789bead241a99d7d5c383ff9d49c5e961a4"
    )  # Zohran Mamdani token, from https://app.seer.pm/markets/100/who-will-win-the-new-york-city-mayoral-election-of-2025-2/?outcome=Zohran+Mamdani
    collateral_token_contract = init_collateral_token_contract(
        outcome_token_contract, web3=local_web3
    )
    assert isinstance(collateral_token_contract, ContractWrapped1155BaseClass)
    collateral_token_contract_on_gnosis_chain = to_gnosis_chain_contract(
        collateral_token_contract
    )
    assert isinstance(
        collateral_token_contract_on_gnosis_chain, ContractWrapped1155OnGnosisChain
    )
