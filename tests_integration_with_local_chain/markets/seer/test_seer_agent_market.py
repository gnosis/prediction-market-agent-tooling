from unittest.mock import Mock, patch

import pytest
from cowdao_cowpy.cow.swap import CompletedOrder
from cowdao_cowpy.order_book.generated.model import UID
from eth_account import Account
from web3 import Web3

from prediction_market_agent_tooling.config import APIKeys
from prediction_market_agent_tooling.gtypes import (
    USD,
    ChecksumAddress,
    OutcomeStr,
    OutcomeToken,
    OutcomeWei,
    Wei,
    private_key_type,
)
from prediction_market_agent_tooling.markets.agent_market import (
    FilterBy,
    QuestionType,
    SortBy,
)
from prediction_market_agent_tooling.markets.data_models import Resolution
from prediction_market_agent_tooling.markets.seer.seer import SeerAgentMarket
from prediction_market_agent_tooling.markets.seer.seer_subgraph_handler import (
    SeerSubgraphHandler,
)
from prediction_market_agent_tooling.markets.seer.swap_pool_handler import (
    SwapPoolHandler,
)
from prediction_market_agent_tooling.tools.contract import (
    init_collateral_token_contract,
    to_gnosis_chain_contract,
)
from prediction_market_agent_tooling.tools.hexbytes_custom import HexBytes
from prediction_market_agent_tooling.tools.tokens.auto_deposit import (
    auto_deposit_collateral_token,
)
from prediction_market_agent_tooling.tools.utils import check_not_none


def test_seer_get_resolution(seer_subgraph_handler_test: SeerSubgraphHandler) -> None:
    # closed market, answer no
    market_id = HexBytes("0x83f012a56083ceaa846730f89c69e363230ae9a6")
    market = seer_subgraph_handler_test.get_market_by_id(market_id=market_id)
    # market = seer_subgraph_handler_test.dummy(market_id=market_id)
    agent_market = SeerAgentMarket.from_data_model_with_subgraph(
        market,
        seer_subgraph=seer_subgraph_handler_test,
        must_have_prices=False,
    )
    agent_market = check_not_none(agent_market)
    assert market.is_resolved
    assert agent_market.is_resolved()
    assert agent_market.resolution == Resolution(
        outcome=OutcomeStr("No"), invalid=False
    )


def test_seer_place_bet(
    local_web3: Web3,
    test_keys: APIKeys,
    seer_subgraph_handler_test: SeerSubgraphHandler,
) -> None:
    # We fetch the market with the highest liquidity because we expect quotes to be available for all outcome tokens.
    markets = SeerSubgraphHandler().get_markets(
        filter_by=FilterBy.OPEN,
        limit=1,
        sort_by=SortBy.HIGHEST_LIQUIDITY,
        question_type=QuestionType.BINARY,
    )
    market_data_model = markets[0]
    agent_market = SeerAgentMarket.from_data_model_with_subgraph(
        market_data_model,
        seer_subgraph=seer_subgraph_handler_test,
        must_have_prices=False,
    )
    agent_market = check_not_none(agent_market)
    amount = USD(10.0)

    with pytest.raises(Exception):
        # We expect an exception from Cow since test accounts don't have enough funds.
        agent_market.place_bet(
            api_keys=test_keys,
            outcome=agent_market.outcomes[0],
            amount=amount,
            auto_deposit=False,
            web3=local_web3,
        )


def test_seer_place_bet_via_pools(
    local_web3: Web3,
    test_keys: APIKeys,
    seer_subgraph_handler_test: SeerSubgraphHandler,
) -> None:
    # We fetch the market with the highest liquidity because we expect quotes to be available for all outcome tokens.
    markets = SeerSubgraphHandler().get_markets(
        filter_by=FilterBy.OPEN,
        limit=1,
        sort_by=SortBy.HIGHEST_LIQUIDITY,
        question_type=QuestionType.BINARY,
    )
    market_data_model = markets[0]
    agent_market = SeerAgentMarket.from_data_model_with_subgraph(
        market_data_model,
        seer_subgraph=seer_subgraph_handler_test,
        must_have_prices=True,
    )
    agent_market = check_not_none(agent_market)
    outcome = agent_market.outcomes[0]
    mock_completed_order = Mock(spec=CompletedOrder)
    mock_completed_order.uid = UID(root="1234")
    # Mock swap_tokens_waiting to throw a TimeoutError immediately
    with patch(
        "prediction_market_agent_tooling.markets.seer.seer.swap_tokens_waiting",
        return_value=(None, mock_completed_order),
    ), patch(
        "prediction_market_agent_tooling.markets.seer.seer.wait_for_order_completion",
        side_effect=TimeoutError("Mocked timeout error"),
    ):
        agent_market.place_bet(
            outcome=outcome,
            amount=USD(1.0),
            auto_deposit=True,
            web3=local_web3,
            api_keys=test_keys,
        )

    final_outcome_token_balance = agent_market.get_token_balance(
        user_id=test_keys.bet_from_address, outcome=outcome, web3=local_web3
    )
    assert final_outcome_token_balance > 0


def prepare_seer_swap_test(
    local_web3: Web3,
    test_keys: APIKeys,
    deposit_collateral: bool = False,
    market_id: HexBytes | None = None,
) -> tuple[
    SeerAgentMarket, ChecksumAddress, int, ChecksumAddress, OutcomeWei, OutcomeToken
]:
    """Prepare common test setup for swap tests."""
    amount_wei = OutcomeToken(1).as_outcome_wei
    market = (
        SeerAgentMarket.get_markets(
            limit=1,
            sort_by=SortBy.HIGHEST_LIQUIDITY,
            filter_by=FilterBy.OPEN,
            question_type=QuestionType.BINARY,
        )[0]
        if market_id is None
        else SeerAgentMarket.from_data_model_with_subgraph(
            SeerSubgraphHandler().get_market_by_id(market_id),
            SeerSubgraphHandler(),
            True,
        )
    )
    assert market is not None

    sell_token = market.collateral_token_contract_address_checksummed
    outcome_idx = 0
    buy_token = market.wrapped_tokens[outcome_idx]

    # assert there is liquidity to swap
    assert market.has_liquidity_for_outcome(market.outcomes[outcome_idx])

    if deposit_collateral:
        # Fund test account
        collateral_token_contract = to_gnosis_chain_contract(
            init_collateral_token_contract(
                market.collateral_token_contract_address_checksummed, local_web3
            )
        )

        auto_deposit_collateral_token(
            collateral_token_contract=collateral_token_contract,
            collateral_amount_wei_or_usd=amount_wei.as_wei,
            api_keys=test_keys,
            web3=local_web3,
        )

    initial_outcome_token_balance = market.get_token_balance(
        user_id=test_keys.bet_from_address,
        outcome=market.outcomes[outcome_idx],
        web3=local_web3,
    )

    return (
        market,
        sell_token,
        outcome_idx,
        buy_token,
        amount_wei,
        initial_outcome_token_balance,
    )


def test_seer_swap_via_pools(local_web3: Web3, test_keys: APIKeys) -> None:
    (
        market,
        sell_token,
        outcome_idx,
        buy_token,
        amount_wei,
        initial_outcome_token_balance,
    ) = prepare_seer_swap_test(local_web3, test_keys, deposit_collateral=True)

    SwapPoolHandler(
        api_keys=test_keys,
        market_id=market.id,
        collateral_token_address=market.collateral_token_contract_address_checksummed,
    ).buy_or_sell_outcome_token(
        token_in=sell_token,
        token_out=buy_token,
        amount_wei=Wei(amount_wei.value),
        web3=local_web3,
    )

    final_outcome_token_balance = market.get_token_balance(
        user_id=test_keys.bet_from_address,
        outcome=market.outcomes[outcome_idx],
        web3=local_web3,
    )
    assert final_outcome_token_balance > initial_outcome_token_balance


def test_seer_swap_via_pools_fails_when_no_balance(
    local_web3: Web3,
) -> None:
    account = Account.create()

    test_keys_with_no_balance = APIKeys(
        BET_FROM_PRIVATE_KEY=private_key_type(account.key.to_0x_hex()),
        SAFE_ADDRESS=None,
    )

    market, sell_token, _, buy_token, amount_wei, _ = prepare_seer_swap_test(
        local_web3, test_keys_with_no_balance, deposit_collateral=False
    )

    with pytest.raises(Exception):
        SwapPoolHandler(
            api_keys=test_keys_with_no_balance,
            market_id=market.id,
            collateral_token_address=market.collateral_token_contract_address_checksummed,
        ).buy_or_sell_outcome_token(
            token_in=sell_token,
            token_out=buy_token,
            amount_wei=Wei(amount_wei.value),
            web3=local_web3,
        )

def test_seer_redeem_scalar(seer_subgraph_handler_test: SeerSubgraphHandler) -> None:
    # ToDo
    safe_address = Web3.to_checksum_address("0xdF99b89934f697f295fDf132Ec5174656bC088BD")
    market_id = HexBytes("0x8517e637b15246d8ae0b384bf53c601a99d8b16f")
    #  fork curr block gnosis
    market = seer_subgraph_handler_test.get_market_by_id(market_id=market_id)
    agent_market = SeerAgentMarket.from_data_model_with_subgraph(market, seer_subgraph=seer_subgraph_handler_test, must_have_prices=False)
    keys = APIKeys(SAFE_ADDRESS=safe_address)
    TENDERLY_URL = "https://virtual.gnosis.eu.rpc.tenderly.co/7f5c6362-34d2-46a8-9b5a-3c189de74c32"
    w3 = Web3(Web3.HTTPProvider(TENDERLY_URL))
    import os
    os.environ['GNOSIS_RPC_URL'] = TENDERLY_URL
    # ToDo mock web3
    agent_market.redeem_winnings(keys)
    #  call redeem on market id
    assert False

