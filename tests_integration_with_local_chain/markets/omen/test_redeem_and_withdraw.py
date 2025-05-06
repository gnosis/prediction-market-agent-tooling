import time
from datetime import timedelta

from ape_test import TestAccount
from web3 import Web3

from prediction_market_agent_tooling.config import APIKeys
from prediction_market_agent_tooling.gtypes import USD, private_key_type, xDai
from prediction_market_agent_tooling.markets.omen.data_models import (
    OMEN_BINARY_MARKET_OUTCOMES,
)
from prediction_market_agent_tooling.markets.omen.omen import (
    OmenAgentMarket,
    OmenMarket,
    binary_omen_buy_outcome_tx,
    omen_create_market_tx,
)
from prediction_market_agent_tooling.markets.omen.omen_contracts import (
    OmenConditionalTokenContract,
    sDaiContract,
)
from prediction_market_agent_tooling.markets.omen.omen_resolving import (
    omen_resolve_market_tx,
    omen_submit_invalid_answer_market_tx,
)
from prediction_market_agent_tooling.tools.tokens.auto_withdraw import (
    auto_withdraw_collateral_token,
)
from prediction_market_agent_tooling.tools.utils import check_not_none, utcnow
from tests.utils import mint_new_block


def test_redeem_and_withdraw(
    accounts: list[TestAccount],
    local_web3: Web3,
) -> None:
    # Get three accounts, one will create a market with liquidity, and the two will place bets in opposing directions.
    account = accounts[9]
    api_keys = APIKeys(
        BET_FROM_PRIVATE_KEY=private_key_type(account.private_key),
        SAFE_ADDRESS=None,
    )

    # Update chain's state with a dummy block.
    mint_new_block(api_keys, local_web3)

    # Create the market.
    close_in = 10
    question = f"Will job X be completed in {close_in} seconds from now?"
    created_time = utcnow()
    closing_time = created_time + timedelta(seconds=close_in)
    funds = USD(10)
    fee_perc = 0.02
    finalization_wait_time_seconds = 1
    category = "cryptocurrency"
    language = "en"
    created_market = omen_create_market_tx(
        api_keys=api_keys,
        initial_funds=funds,
        fee_perc=fee_perc,
        question=question,
        closing_time=closing_time,
        category=category,
        language=language,
        outcomes=OMEN_BINARY_MARKET_OUTCOMES,
        finalization_timeout=timedelta(seconds=finalization_wait_time_seconds),
        collateral_token_address=sDaiContract().address,
        auto_deposit=True,
        web3=local_web3,
    )
    print(
        f"Market created at {created_market.market_event.fixed_product_market_maker_checksummed}"
    )

    # Initialize OmenMarket and OmenAgentMarket out of it, so we can use it with our standard helper functions.
    omen_market = OmenMarket.from_created_market(created_market)
    agent_market = OmenAgentMarket.from_data_model(omen_market)

    # Buy YES tokens
    bet_size = USD(1)
    binary_omen_buy_outcome_tx(
        api_keys,
        bet_size,
        agent_market,
        binary_outcome=False,
        auto_deposit=True,
        web3=local_web3,
    )

    # Wait for market's closing time
    time.sleep(close_in * 1.2)
    # Do a dummy block again, so the time in the contract is updated and it knows it's opened already.
    mint_new_block(api_keys, local_web3)

    # Submit invalid answer on reality.
    omen_submit_invalid_answer_market_tx(
        api_keys,
        omen_market,
        bond=xDai(0.001),
        web3=local_web3,
    )

    # Wait for the finalization.
    time.sleep(finalization_wait_time_seconds * 1.2)
    # Update the time in the chain again.
    mint_new_block(api_keys, local_web3)

    # Resolve the market.
    omen_resolve_market_tx(api_keys, omen_market, local_web3)

    # Redeem positions.
    # Note: Usually we just take all positions from subgraph and redeem them, here we manually redeem the ones we should have now.
    conditional_token_contract = OmenConditionalTokenContract()
    condition_event = check_not_none(
        created_market.condition_event,
        "Should not be None here as this was a freshly created market.",
    )

    before_redeem_balance = sDaiContract().balanceOf(
        api_keys.bet_from_address, local_web3
    )
    redeem_event = conditional_token_contract.redeemPositions(
        api_keys=api_keys,
        collateral_token_address=agent_market.collateral_token_contract_address_checksummed,
        condition_id=condition_event.conditionId,
        index_sets=omen_market.condition.index_sets,
        web3=local_web3,
    )
    after_redeem_balance = sDaiContract().balanceOf(
        api_keys.bet_from_address, local_web3
    )

    assert redeem_event.payout == after_redeem_balance - before_redeem_balance

    auto_withdraw_collateral_token(
        sDaiContract(),
        redeem_event.payout,
        api_keys,
        local_web3,
    )

    after_withdraw_balance = sDaiContract().balanceOf(
        api_keys.bet_from_address, local_web3
    )

    assert after_withdraw_balance == before_redeem_balance
