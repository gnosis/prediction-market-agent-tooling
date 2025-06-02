import time
from datetime import timedelta

from ape_test import TestAccount
from web3 import Web3

from prediction_market_agent_tooling.config import APIKeys
from prediction_market_agent_tooling.gtypes import (
    USD,
    CollateralToken,
    private_key_type,
    xDai,
)
from prediction_market_agent_tooling.markets.omen.data_models import (
    OMEN_BINARY_MARKET_OUTCOMES,
    OMEN_FALSE_OUTCOME,
    OMEN_TRUE_OUTCOME,
)
from prediction_market_agent_tooling.markets.omen.omen import (
    OmenAgentMarket,
    OmenMarket,
    binary_omen_buy_outcome_tx,
    omen_create_market_tx,
)
from prediction_market_agent_tooling.markets.omen.omen_contracts import (
    OmenConditionalTokenContract,
    WrappedxDaiContract,
)
from prediction_market_agent_tooling.markets.omen.omen_resolving import (
    omen_resolve_market_tx,
    omen_submit_invalid_answer_market_tx,
)
from prediction_market_agent_tooling.tools.balances import get_balances
from prediction_market_agent_tooling.tools.utils import check_not_none, utcnow
from tests.utils import mint_new_block


def test_redeem_invalid_market(
    eoa_accounts: list[TestAccount],
    local_web3: Web3,
) -> None:
    """
    TLDR: If the market is invalid, we can normally redeem it.
    """

    # Get three accounts, one will create a market with liquidity, and the two will place bets in opposing directions.
    account_A, account_B, account_C = eoa_accounts[7], eoa_accounts[8], eoa_accounts[9]
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
    funds = USD(10)
    funds_t = CollateralToken(funds.value)  # In this test, 1 USD = 1 Token
    fee_perc = 0.02
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
    assert agent_market.get_liquidity(local_web3) == funds_t

    # Buy YES tokens from account B
    bet_size = USD(1)
    binary_omen_buy_outcome_tx(
        api_keys_B,
        bet_size,
        agent_market,
        outcome=OMEN_FALSE_OUTCOME,
        auto_deposit=True,
        web3=local_web3,
    )
    balance_after_buying_B = get_balances(api_keys_B.bet_from_address, local_web3).total
    assert (
        balance_after_buying_B < starting_balance_B
    ), "Balance of B should have been lowered from betting"

    # Buy NO tokens from account C
    binary_omen_buy_outcome_tx(
        api_keys_C,
        bet_size,
        agent_market,
        outcome=OMEN_TRUE_OUTCOME,
        auto_deposit=True,
        web3=local_web3,
    )
    balance_after_buying_C = get_balances(api_keys_C.bet_from_address, local_web3).total
    assert (
        balance_after_buying_C < starting_balance_C
    ), "Balance of C should have been lowered from betting"

    # Wait for market's closing time
    time.sleep(close_in * 1.2)
    # Do a dummy block again, so the time in the contract is updated and it knows it's opened already.
    mint_new_block(api_keys_A, local_web3)

    # Submit invalid answer on reality.
    omen_submit_invalid_answer_market_tx(
        api_keys_A,
        omen_market,
        bond=xDai(0.001),
        web3=local_web3,
    )

    # Wait for the finalization.
    time.sleep(finalization_wait_time_seconds * 1.2)
    # Update the time in the chain again.
    mint_new_block(api_keys_A, local_web3)

    # Resolve the market.
    omen_resolve_market_tx(api_keys_A, omen_market, local_web3)

    # Redeem positions.
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
    ending_balance_B, ending_balance_C = (
        get_balances(api_keys_B.bet_from_address, local_web3).total,
        get_balances(api_keys_C.bet_from_address, local_web3).total,
    )

    account_B_difference = ending_balance_B - starting_balance_B
    account_C_difference = ending_balance_C - starting_balance_C

    print(f"Account B ending difference: {account_B_difference}.")
    print(f"Account C ending difference: {account_C_difference}.")

    assert (
        -agent_market.get_usd_in_token(bet_size)
        < account_B_difference
        < CollateralToken(0)
    ), "Assumption was that B will get most of the money back but would incur a loss because he bought tokens at a higher price than 0.5."
    assert account_C_difference > CollateralToken(
        0
    ), "Assumption was that C will be profitable because he was buying the cheaper tokens."
