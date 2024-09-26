import time
from datetime import timedelta

import pytest
from ape_test import TestAccount
from web3 import Web3

from prediction_market_agent_tooling.config import APIKeys
from prediction_market_agent_tooling.gtypes import private_key_type, xdai_type
from prediction_market_agent_tooling.markets.data_models import Resolution
from prediction_market_agent_tooling.markets.omen.data_models import (
    OMEN_BINARY_MARKET_OUTCOMES,
)
from prediction_market_agent_tooling.markets.omen.omen import (
    OmenAgentMarket,
    OmenMarket,
    binary_omen_buy_outcome_tx,
    binary_omen_sell_outcome_tx,
    omen_create_market_tx,
    omen_remove_fund_market_tx,
)
from prediction_market_agent_tooling.markets.omen.omen_contracts import (
    OMEN_DEFAULT_MARKET_FEE_PERC,
    OmenConditionalTokenContract,
    WrappedxDaiContract,
)
from prediction_market_agent_tooling.markets.omen.omen_resolving import (
    omen_resolve_market_tx,
    omen_submit_answer_market_tx,
)
from prediction_market_agent_tooling.tools.balances import get_balances
from prediction_market_agent_tooling.tools.contract import DebuggingContract
from prediction_market_agent_tooling.tools.utils import check_not_none, utcnow


def test_stealing_on_markets(
    accounts: list[TestAccount],
    local_web3: Web3,
) -> None:
    # Get two accounts, one will create a job market (A) and one will try to sabotage it (B)
    account_A, account_B = accounts[0], accounts[1]
    api_keys_A, api_keys_B = APIKeys(
        BET_FROM_PRIVATE_KEY=private_key_type(account_A.private_key), SAFE_ADDRESS=None
    ), APIKeys(
        BET_FROM_PRIVATE_KEY=private_key_type(account_B.private_key), SAFE_ADDRESS=None
    )
    print(f"{api_keys_A.bet_from_address=}, {api_keys_B.bet_from_address=}")

    # Update chain's state with a dummy block.
    DebuggingContract().inc(api_keys_A, local_web3)

    # Get their starting balances, so we can compare them with their ending balances.
    starting_balance_A, starting_balance_B = (
        get_balances(api_keys_A.bet_from_address, local_web3).total,
        get_balances(api_keys_B.bet_from_address, local_web3).total,
    )

    # Create the market.
    close_in = 10
    question = f"Will job X be completed in {close_in} seconds from now?"
    created_time = utcnow()
    closing_time = created_time + timedelta(seconds=close_in)
    funds = xdai_type(10)
    finalization_wait_time_seconds = 1
    category = "cryptocurrency"
    language = "en"
    created_market = omen_create_market_tx(
        api_keys=api_keys_A,
        initial_funds=funds,
        fee_perc=OMEN_DEFAULT_MARKET_FEE_PERC,
        question=question,
        closing_time=closing_time,
        category=category,
        language=language,
        outcomes=OMEN_BINARY_MARKET_OUTCOMES,
        finalization_timeout=timedelta(seconds=finalization_wait_time_seconds),
        collateral_token_address=WrappedxDaiContract().address,
        auto_deposit=True,
        web3=local_web3,
    )
    print(
        f"Market created at {created_market.market_event.fixed_product_market_maker_checksummed}"
    )

    # Initialize OmenMarket and OmenAgentMarket out of it, so we can use it with our standard helper functions.
    omen_market = OmenMarket.from_created_market(created_market)
    agent_market = OmenAgentMarket.from_data_model(omen_market)
    balance_after_market_creation_A, balance_after_market_creation_B = (
        get_balances(api_keys_A.bet_from_address, local_web3).total,
        get_balances(api_keys_B.bet_from_address, local_web3).total,
    )
    assert (
        balance_after_market_creation_A < starting_balance_A
    ), "Starting balance of A should have been lowered"

    # Buy YES tokens from accout B (attacker) -- removing profit from any real agent that'd like to complete the job.
    buy_yes_for_b = xdai_type(5)
    binary_omen_buy_outcome_tx(
        api_keys_B,
        buy_yes_for_b,
        agent_market,
        binary_outcome=True,
        auto_deposit=True,
        web3=local_web3,
    )
    balance_after_buying_A, balance_after_buying_B = (
        get_balances(api_keys_A.bet_from_address, local_web3).total,
        get_balances(api_keys_B.bet_from_address, local_web3).total,
    )
    assert (
        balance_after_buying_B < starting_balance_B
    ), "Balance of B should have be lowered from betting"

    # Account A detects this and removes remaining liquidity, so the attacker is locked-in and will loose money unless he completes the job.
    omen_remove_fund_market_tx(api_keys_A, agent_market, shares=None, web3=local_web3)
    balance_after_removing_funding_A, balance_after_removing_funding_B = (
        get_balances(api_keys_A.bet_from_address, local_web3).total,
        get_balances(api_keys_B.bet_from_address, local_web3).total,
    )
    assert (
        balance_after_market_creation_A
        < balance_after_removing_funding_A
        < starting_balance_A
    ), "Balance after removing the liquidity should be higher than after market creation (because some liquidity can be withdrawn right away), but lower than before market creation (because some liquidity is now locked for the attacker's bet)"

    # Buying or selling tokens after the liquidity is removed will fail.
    with pytest.raises(Exception) as e_buying:
        binary_omen_buy_outcome_tx(
            api_keys_B,
            buy_yes_for_b,
            agent_market,
            binary_outcome=True,
            auto_deposit=True,
            web3=local_web3,
        )
    sell_yes_for_b = xdai_type(1)
    with pytest.raises(Exception) as e_selling:
        binary_omen_sell_outcome_tx(
            api_keys_B,
            sell_yes_for_b,
            agent_market,
            binary_outcome=True,
            auto_withdraw=True,
            web3=local_web3,
        )
    balance_after_failed_trading_A, balance_after_failed_trading_B = (
        get_balances(api_keys_A.bet_from_address, local_web3).total,
        get_balances(api_keys_B.bet_from_address, local_web3).total,
    )
    assert (
        balance_after_failed_trading_B == balance_after_buying_B
    ), "Balance after failed trading should be the same as after buying of tokens in the beginning, because nothing should have happened."

    # Wait for market's closing time
    time.sleep(close_in * 1.1)
    # Do a dummy block again, so the time in the contract is updated and it knows it's opened already.
    DebuggingContract().inc(api_keys_A, local_web3)

    # Submit answer on reality.
    omen_submit_answer_market_tx(
        api_keys_A,
        omen_market,
        Resolution.NO,
        bond=xdai_type(0.001),
        web3=local_web3,
    )

    # Wait for the finalization.
    time.sleep(finalization_wait_time_seconds * 1.1)
    # Update the time in the chain again.
    DebuggingContract().inc(api_keys_A, local_web3)

    # Resolve the market.
    omen_resolve_market_tx(api_keys_A, omen_market, local_web3)

    # Redeem positions from both accounts.
    # Note: Usually we just take all positions from subgraph and redeem them, here we manualy redeem the ones we should have now.
    conditional_token_contract = OmenConditionalTokenContract()
    condition_event = check_not_none(
        created_market.condition_event,
        "Should not be None here as this was a freshly created market.",
    )
    conditional_token_contract.redeemPositions(
        api_keys=api_keys_A,
        collateral_token_address=agent_market.collateral_token_contract_address_checksummed,
        condition_id=condition_event.conditionId,
        index_sets=omen_market.condition.index_sets,
        web3=local_web3,
    )
    conditional_token_contract.redeemPositions(
        api_keys=api_keys_B,
        collateral_token_address=agent_market.collateral_token_contract_address_checksummed,
        condition_id=condition_event.conditionId,
        index_sets=omen_market.condition.index_sets,
        web3=local_web3,
    )

    # Check who is the winner in the end/
    ending_balance_A, ending_balance_B = (
        get_balances(api_keys_A.bet_from_address, local_web3).total,
        get_balances(api_keys_B.bet_from_address, local_web3).total,
    )

    assert (
        ending_balance_A > starting_balance_A
    ), "Assumption was that A will receive B's money."
    assert (
        ending_balance_B < starting_balance_A
    ), "Assumption was that B will loose the money he gambled by trying to steal from real job completors."

    print(
        f"Account A (job creator) ending difference: {ending_balance_A - starting_balance_A}."
    )
    print(
        f"Account B (attacker) ending difference: {ending_balance_B - starting_balance_B}."
    )
