from web3 import Web3

from prediction_market_agent_tooling.config import APIKeys
from prediction_market_agent_tooling.gtypes import (
    ChecksumAddress,
    PrivateKey,
    SecretStr,
    Wei,
    xDai,
)
from prediction_market_agent_tooling.markets.agent_market import (
    ConditionalFilterType,
    FilterBy,
    QuestionType,
    SortBy,
)
from prediction_market_agent_tooling.markets.seer.seer import SeerAgentMarket
from prediction_market_agent_tooling.markets.seer.seer_contracts import GnosisRouter
from prediction_market_agent_tooling.markets.seer.seer_subgraph_handler import (
    SeerSubgraphHandler,
)
from prediction_market_agent_tooling.tools.contract import (
    ContractERC20OnGnosisChain,
    init_collateral_token_contract,
    to_gnosis_chain_contract,
)
from prediction_market_agent_tooling.tools.cow.cow_order import handle_allowance
from prediction_market_agent_tooling.tools.tokens.auto_deposit import (
    auto_deposit_collateral_token,
)
from prediction_market_agent_tooling.tools.utils import check_not_none
from tests_integration_with_local_chain.conftest import create_and_fund_random_account


def fetch_wrapped_token_balances(
    address: ChecksumAddress, wrapped_tokens: list[ChecksumAddress], web3: Web3
) -> dict[ChecksumAddress, Wei]:
    return {
        token_address: ContractERC20OnGnosisChain(address=token_address).balanceOf(
            for_address=address, web3=web3
        )
        for token_address in wrapped_tokens
    }


def test_seer_mint_child_outcome_tokens(
    seer_subgraph_handler_test: SeerSubgraphHandler,
    test_keys: APIKeys,
    local_web3: Web3,
) -> None:
    fresh_account = create_and_fund_random_account(web3=local_web3)
    keys = APIKeys(BET_FROM_PRIVATE_KEY=PrivateKey(SecretStr(fresh_account.key.hex())))
    market = seer_subgraph_handler_test.get_markets(
        filter_by=FilterBy.OPEN,
        sort_by=SortBy.HIGHEST_LIQUIDITY,
        limit=1,
        question_type=QuestionType.CATEGORICAL,
    )[0]

    market_agent = SeerAgentMarket.from_data_model_with_subgraph(
        model=market,
        seer_subgraph=seer_subgraph_handler_test,
        must_have_prices=False,
    )
    market_agent = check_not_none(market_agent)
    # 0. Auto-deposit sDAI
    amount_wei = Wei(xDai(1.0).as_xdai_wei.value)
    collateral_token_contract = to_gnosis_chain_contract(
        init_collateral_token_contract(
            market_agent.collateral_token_contract_address_checksummed, web3=local_web3
        )
    )

    initial_wrapped_token_balances = fetch_wrapped_token_balances(
        address=keys.bet_from_address,
        wrapped_tokens=market_agent.wrapped_tokens,
        web3=local_web3,
    )

    auto_deposit_collateral_token(
        collateral_token_contract=collateral_token_contract,
        collateral_amount_wei_or_usd=amount_wei,
        api_keys=keys,
        web3=local_web3,
    )

    handle_allowance(
        api_keys=keys,
        sell_token=collateral_token_contract.address,
        amount_to_check_wei=amount_wei,
        for_address=GnosisRouter().address,
        web3=local_web3,
    )

    GnosisRouter().split_position(
        api_keys=keys,
        collateral_token=collateral_token_contract.address,
        market_id=Web3.to_checksum_address(market_agent.id),
        amount=amount_wei,
        web3=local_web3,
    )

    # Assert outcome tokens were transferred
    final_wrapped_token_balances = fetch_wrapped_token_balances(
        address=keys.bet_from_address,
        wrapped_tokens=market_agent.wrapped_tokens,
        web3=local_web3,
    )

    for token_address in market_agent.wrapped_tokens:
        initial_token_balance: Wei = initial_wrapped_token_balances[token_address]
        final_token_balance: Wei = final_wrapped_token_balances[token_address]
        minted_token_balance = final_token_balance - initial_token_balance
        assert minted_token_balance == amount_wei


def test_init_collateral_conditional_market(
    local_web3: Web3,
    test_keys: APIKeys,
    seer_subgraph_handler_test: SeerSubgraphHandler,
) -> None:
    fresh_account = create_and_fund_random_account(web3=local_web3)
    keys = APIKeys(BET_FROM_PRIVATE_KEY=PrivateKey(SecretStr(fresh_account.key.hex())))
    # It should mint collateral tokens from parent market.
    child_market = seer_subgraph_handler_test.get_markets(
        conditional_filter_type=ConditionalFilterType.ONLY_CONDITIONAL,
        sort_by=SortBy.HIGHEST_LIQUIDITY,
        filter_by=FilterBy.OPEN,
    )[0]

    amount_wei = Wei(xDai(1.0).as_xdai_wei.value)

    collateral_token_contract = to_gnosis_chain_contract(
        init_collateral_token_contract(
            child_market.collateral_token_contract_address_checksummed, web3=local_web3
        )
    )
    auto_deposit_collateral_token(
        collateral_token_contract=collateral_token_contract,
        collateral_amount_wei_or_usd=amount_wei,
        api_keys=keys,
        web3=local_web3,
    )
    # assert collateral tokens were transferred
    token_balance = ContractERC20OnGnosisChain(
        address=child_market.collateral_token_contract_address_checksummed
    ).balanceOf(keys.bet_from_address, web3=local_web3)
    # >= to account for surplus changes when auto-depositing
    assert token_balance >= amount_wei
