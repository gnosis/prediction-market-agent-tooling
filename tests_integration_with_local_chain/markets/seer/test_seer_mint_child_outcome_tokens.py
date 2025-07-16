from web3 import Web3

from prediction_market_agent_tooling.config import APIKeys
from prediction_market_agent_tooling.gtypes import xDai, Wei
from prediction_market_agent_tooling.markets.agent_market import (
    SortBy,
    MarketType,
    FilterBy,
)
from prediction_market_agent_tooling.markets.seer.seer import SeerAgentMarket
from prediction_market_agent_tooling.markets.seer.seer_contracts import GnosisRouter
from prediction_market_agent_tooling.markets.seer.seer_subgraph_handler import (
    SeerSubgraphHandler,
)
from prediction_market_agent_tooling.tools.contract import (
    to_gnosis_chain_contract,
    init_collateral_token_contract,
    ContractERC20OnGnosisChain,
)
from prediction_market_agent_tooling.tools.cow.cow_order import handle_allowance
from prediction_market_agent_tooling.tools.tokens.auto_deposit import (
    auto_deposit_collateral_token,
)


def test_seer_mint_child_outcome_tokens(
    seer_subgraph_handler_test: SeerSubgraphHandler,
    test_keys: APIKeys,
    local_web3: Web3,
) -> None:
    market = seer_subgraph_handler_test.get_markets(
        filter_by=FilterBy.OPEN,
        sort_by=SortBy.HIGHEST_LIQUIDITY,
        limit=1,
        market_type=MarketType.CATEGORICAL,
    )[0]

    market_agent = SeerAgentMarket.from_data_model_with_subgraph(
        model=market,
        seer_subgraph=seer_subgraph_handler_test,
        must_have_prices=False,
    )
    # 0. Auto-deposit sDAI
    amount_wei = Wei(xDai(1.0).as_xdai_wei.value)
    collateral_token_contract = to_gnosis_chain_contract(
        init_collateral_token_contract(
            market_agent.collateral_token_contract_address_checksummed, web3=local_web3
        )
    )
    auto_deposit_collateral_token(
        collateral_token_contract=collateral_token_contract,
        collateral_amount_wei_or_usd=amount_wei,
        api_keys=test_keys,
        web3=local_web3,
    )

    handle_allowance(
        api_keys=test_keys,
        sell_token=collateral_token_contract.address,
        amount_wei=amount_wei,
        for_address=GnosisRouter().address,
        web3=local_web3,
    )

    GnosisRouter().split_position(
        api_keys=test_keys,
        collateral_token=collateral_token_contract.address,
        market_id=Web3.to_checksum_address(market_agent.id),
        amount=amount_wei,
        web3=local_web3,
    )

    # Assert outcome tokens were transferred
    for token_address in market_agent.wrapped_tokens:
        token_balance = ContractERC20OnGnosisChain(address=token_address).balanceOf(
            test_keys.bet_from_address, web3=local_web3
        )
        assert token_balance == amount_wei
