import time
from datetime import timedelta

import numpy as np
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
    omen_create_market_tx,
    omen_fund_market_tx,
    omen_remove_fund_market_tx,
)
from prediction_market_agent_tooling.markets.omen.omen_contracts import (
    OmenConditionalTokenContract,
    WrappedxDaiContract,
)
from prediction_market_agent_tooling.markets.omen.omen_resolving import (
    omen_resolve_market_tx,
    omen_submit_answer_market_tx,
)
from prediction_market_agent_tooling.tools.balances import get_balances
from prediction_market_agent_tooling.tools.utils import check_not_none, utcnow
from prediction_market_agent_tooling.tools.web3_utils import xdai_to_wei
from tests.utils import mint_new_block


def test_where_fees_go(
    accounts: list[TestAccount],
    local_web3: Web3,
) -> None:
    """
    TLDR: Fee is not added to the liquidity. Fee will be split to liquidity providers.
    """

    # Get three accounts, one will create a market with liquidity and huge fees, second one will add some more liquidity, and the last one will bet there.
    account_A, account_B, account_C = accounts[4], accounts[5], accounts[6]
    api_keys_A, api_keys_B, api_keys_C = (
        APIKeys(
            BET_FROM_PRIVATE_KEY=private_key_type(account_A.private_key),
            SAFE_ADDRESS=None,
        ),
        APIKeys(
            BET_FROM_PRIVATE_KEY=private_key_type(account_B.private_key),
            SAFE_ADDRESS=None,
        ),
        APIKeys(
            BET_FROM_PRIVATE_KEY=private_key_type(account_C.private_key),
            SAFE_ADDRESS=None,
        ),
    )
    print(
        f"{api_keys_A.bet_from_address=}, {api_keys_B.bet_from_address=}, {api_keys_C.bet_from_address=}"
    )

    # Update chain's state with a dummy block.
    mint_new_block(api_keys_A, local_web3)

    # Get their starting balances, so we can compare them with their ending balances.
    starting_balance_A, starting_balance_B, starting_balance_C = (
        get_balances(api_keys_A.bet_from_address, local_web3).total,
        get_balances(api_keys_B.bet_from_address, local_web3).total,
        get_balances(api_keys_C.bet_from_address, local_web3).total,
    )

    # Create the market.
    close_in = 10
    question = f"Will job X be completed in {close_in} seconds from now?"
    created_time = utcnow()
    closing_time = created_time + timedelta(seconds=close_in)
    funds = xdai_type(1)
    fee_perc = 0.5
    finalization_wait_time_seconds = 1
    category = "cryptocurrency"
    language = "en"
    created_market = omen_create_market_tx(
        api_keys=api_keys_A,
        initial_funds=funds,
        fee_perc=fee_perc,
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
    balance_after_market_creation_A = get_balances(
        api_keys_A.bet_from_address, local_web3
    ).total
    assert (
        balance_after_market_creation_A < starting_balance_A
    ), "Starting balance of A should have been lowered"
    assert agent_market.get_liquidity_in_xdai(local_web3) == funds

    # Add double the liquidity from account B
    additional_funds = xdai_type(funds * 2)
    omen_fund_market_tx(
        api_keys_B,
        agent_market,
        xdai_to_wei(additional_funds),
        auto_deposit=True,
        web3=local_web3,
    )
    balance_after_adding_liquidity_B = get_balances(
        api_keys_B.bet_from_address, local_web3
    ).total
    assert (
        balance_after_adding_liquidity_B < starting_balance_B
    ), "Balance of B should have be lowered from adding liquidity"
    assert agent_market.get_liquidity_in_xdai(local_web3) == funds + additional_funds

    # Buy YES tokens from account C
    # Buy for a lot more than given liquidity, to be a loser because of the fees.
    buy_yes_for_c = xdai_type(funds * 10)
    buyer_binary_outcome = True
    binary_omen_buy_outcome_tx(
        api_keys_C,
        buy_yes_for_c,
        agent_market,
        binary_outcome=buyer_binary_outcome,
        auto_deposit=True,
        web3=local_web3,
    )
    balance_after_buying_C = get_balances(api_keys_C.bet_from_address, local_web3).total
    assert (
        balance_after_buying_C < starting_balance_C
    ), "Balance of B should have be lowered from betting"
    assert (
        agent_market.get_liquidity_in_xdai(local_web3) == funds + additional_funds
    ), "Assumption was that fee is not added to the liquidity of the market"

    # Wait for market's closing time
    time.sleep(close_in * 1.2)
    # Do a dummy block again, so the time in the contract is updated and it knows it's opened already.
    mint_new_block(api_keys_A, local_web3)

    # Submit answer on reality.
    # Make the better be correct, so that we know that balance increase in other account is from fees and not incorrect bets.
    omen_submit_answer_market_tx(
        api_keys_A,
        omen_market,
        Resolution.from_bool(buyer_binary_outcome),
        bond=xdai_type(0.001),
        web3=local_web3,
    )

    # Wait for the finalization.
    time.sleep(finalization_wait_time_seconds * 1.2)
    # Update the time in the chain again.
    mint_new_block(api_keys_A, local_web3)

    # Resolve the market.
    omen_resolve_market_tx(api_keys_A, omen_market, local_web3)

    # Remove liquidity provided by the two accounts.
    omen_remove_fund_market_tx(api_keys_A, agent_market, shares=None, web3=local_web3)
    omen_remove_fund_market_tx(api_keys_B, agent_market, shares=None, web3=local_web3)

    # Redeem positions from all accounts.
    # Note: Usually we just take all positions from subgraph and redeem them, here we manually redeem the ones we should have now.
    conditional_token_contract = OmenConditionalTokenContract()
    condition_event = check_not_none(
        created_market.condition_event,
        "Should not be None here as this was a freshly created market.",
    )

    for api_keys_x in [api_keys_A, api_keys_B, api_keys_C]:
        conditional_token_contract.redeemPositions(
            api_keys=api_keys_x,
            collateral_token_address=agent_market.collateral_token_contract_address_checksummed,
            condition_id=condition_event.conditionId,
            index_sets=omen_market.condition.index_sets,
            web3=local_web3,
        )

    # Check who received what money.
    ending_balance_A, ending_balance_B, ending_balance_C = (
        get_balances(api_keys_A.bet_from_address, local_web3).total,
        get_balances(api_keys_B.bet_from_address, local_web3).total,
        get_balances(api_keys_C.bet_from_address, local_web3).total,
    )

    account_A_difference = ending_balance_A - starting_balance_A
    account_B_difference = ending_balance_B - starting_balance_B
    account_C_difference = ending_balance_C - starting_balance_C

    print(f"Account A ending difference: {account_A_difference}.")
    print(f"Account B ending difference: {account_B_difference}.")
    print(f"Account C ending difference: {account_C_difference}.")

    assert (
        account_A_difference > 0
    ), "Assumption was that A will receive C's fees and will be profitable in the end."
    assert (
        account_B_difference > 0
    ), "Assumption was that B will also receive C's fees and will be profitable in the end."
    assert (
        account_B_difference > account_A_difference
    ), "Assumption was that B will receive more from the fees because he provided more liquidity."
    assert np.isclose(
        account_B_difference, 2 * account_A_difference, atol=1e-2
    ), f"Assumption was that B will receive roughly double the amount because he provided double the liquidity, but {account_B_difference=} {2*account_A_difference=}"
    assert (
        account_C_difference < 0
    ), "Assumption was that even that C was correct, he will lose money because of the huge fees and unreasonable bet size given the liquidity."
