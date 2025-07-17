import pytest

from prediction_market_agent_tooling.config import APIKeys
from prediction_market_agent_tooling.gtypes import Wei
from prediction_market_agent_tooling.markets.seer.data_models import ExactInputSingleParams
from prediction_market_agent_tooling.markets.seer.seer_contracts import SwaprRouterContract
from prediction_market_agent_tooling.markets.seer.seer import SeerAgentMarket
from prediction_market_agent_tooling.tools.contract import ContractERC20OnGnosisChain
from prediction_market_agent_tooling.markets.seer.seer import SortBy
from prediction_market_agent_tooling.markets.seer.seer import FilterBy
from tests.utils import RUN_PAID_TESTS


@pytest.mark.skipif(not RUN_PAID_TESTS, reason="This test costs money to run.")
def test_exact_input_single_actual_transaction():
    """
    Integration test: Get first Seer market, execute an actual swap transaction.
    This test costs money to run.
    """
    # Get the first available Seer market
    markets = SeerAgentMarket.get_markets(limit=1, sort_by=SortBy.HIGHEST_LIQUIDITY, filter_by=FilterBy.OPEN)
    if not markets:
        pytest.skip("No Seer markets available")
    
    market = markets[0]
    print(f"\nTesting with market: {market.question}")
    
    # Get market details
    first_outcome = market.outcomes[0]
    outcome_token = market.get_wrapped_token_for_outcome(first_outcome)
    collateral_token = market.collateral_token_contract_address_checksummed
    
    print(f"Outcome: {first_outcome}")
    print(f"Outcome token: {outcome_token}")
    print(f"Collateral token: {collateral_token}")
    
    # Setup transaction parameters
    api_keys = APIKeys()
    from_address = api_keys.bet_from_address
    amount_to_spend = Wei(1000000)  # Small amount for testing
    
    params = ExactInputSingleParams(
        token_in=collateral_token,
        token_out=outcome_token,
        recipient=from_address,
        amount_in=amount_to_spend,
        amount_out_minimum=Wei(0),
    )
    
    print(f"Executing swap of {amount_to_spend.value / 10**18} collateral tokens")
    
    # Check balances BEFORE transaction
    collateral_contract = ContractERC20OnGnosisChain(address=collateral_token)
    outcome_contract = ContractERC20OnGnosisChain(address=outcome_token)
    
    collateral_balance_before = collateral_contract.balanceOf(from_address)
    outcome_balance_before = outcome_contract.balanceOf(from_address)
    
    print(f"Collateral balance before: {collateral_balance_before.value / 10**18}")
    print(f"Outcome balance before: {outcome_balance_before.value / 10**18}")
    
    router = SwaprRouterContract()
    
    # Execute the actual transaction
    receipt = router.exact_input_single(
        api_keys=api_keys,
        params=params,
    )
    
    print(f"Transaction hash: {receipt.transactionHash.hex()}")
    print(f"Transaction status: {'Success' if receipt.status == 1 else 'Failed'}")
    
    # Check balances AFTER transaction
    collateral_balance_after = collateral_contract.balanceOf(from_address)
    outcome_balance_after = outcome_contract.balanceOf(from_address)
    
    print(f"Collateral balance after: {collateral_balance_after.value / 10**18}")
    print(f"Outcome balance after: {outcome_balance_after.value / 10**18}")
    
    # Verify the transaction actually happened
    assert receipt.status == 1, "Transaction should succeed"
    assert collateral_balance_before.value > collateral_balance_after.value, "Collateral balance should decrease"
    assert outcome_balance_after.value > outcome_balance_before.value, "Outcome balance should increase"
    
    tokens_received = outcome_balance_after.value - outcome_balance_before.value
    print(f"✅ Transaction successful!")
    print(f"Received: {tokens_received / 10**18} outcome tokens")
    print(f"Exchange rate: 1 collateral = {tokens_received / amount_to_spend.value:.4f} outcome tokens")
    
    # Verify we got a reasonable value
    assert tokens_received > 0, "Should receive some tokens"
    
    print("✅ CONFIRMED: Real transaction executed successfully!") 