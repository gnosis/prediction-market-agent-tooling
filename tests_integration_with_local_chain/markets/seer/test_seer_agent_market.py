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
    OutcomeToken,
    OutcomeWei,
    Wei,
    private_key_type,
)
from prediction_market_agent_tooling.markets.agent_market import FilterBy, SortBy
from prediction_market_agent_tooling.markets.agent_market import (
    FilterBy,
    MarketType,
    SortBy,
)
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
from prediction_market_agent_tooling.tools.tokens.auto_deposit import (
    auto_deposit_collateral_token,
)
from prediction_market_agent_tooling.tools.utils import check_not_none


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
        market_types=[MarketType.BINARY],
    )
    market_data_model = markets[0]
    agent_market = SeerAgentMarket.from_data_model_with_subgraph(
        market_data_model,
        seer_subgraph=seer_subgraph_handler_test,
        must_have_prices=False,
    )
    agent_market = check_not_none(agent_market)
    amount = USD(10.0)

    with pytest.raises(Exception) as e:
        # We expect an exception from Cow since test accounts don't have enough funds.
        agent_market.place_bet(
            api_keys=test_keys,
            outcome=agent_market.outcomes[0],
            amount=amount,
            auto_deposit=False,
            web3=local_web3,
        )
    exception_message = str(e)

    assert (
        "InsufficientBalance" in exception_message
        or f"not enough for bet size {amount}" in exception_message
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
        market_types=[MarketType.BINARY],
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
    local_web3: Web3, test_keys: APIKeys, deposit_collateral: bool = False
) -> tuple[
    SeerAgentMarket, ChecksumAddress, int, ChecksumAddress, OutcomeWei, OutcomeToken
]:
    """Prepare common test setup for swap tests."""
    amount_wei = OutcomeToken(1).as_outcome_wei
    market = SeerAgentMarket.get_markets(
        limit=1,
        sort_by=SortBy.HIGHEST_LIQUIDITY,
        filter_by=FilterBy.OPEN,
        fetch_categorical_markets=False,
        fetch_scalar_markets=False,
    )[0]

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
        BET_FROM_PRIVATE_KEY=private_key_type(account.key.hex()), SAFE_ADDRESS=None
    )

    market, sell_token, _, buy_token, amount_wei, _ = prepare_seer_swap_test(
        local_web3, test_keys_with_no_balance, deposit_collateral=False
    )

    with pytest.raises(
        ValueError, match=r"Balance \d+ of \w+ insufficient for trade, required \d+"
    ):
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
