from web3 import Web3

from prediction_market_agent_tooling.tools.contract import (
    ContractWrapped1155BaseClass,
    ContractWrapped1155OnGnosisChain,
    init_collateral_token_contract,
    to_gnosis_chain_contract,
)


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
