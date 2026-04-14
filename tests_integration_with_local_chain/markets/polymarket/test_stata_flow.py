"""End-to-end integration tests for the stataPolUSDCn collateral path.

Exercises on a Polygon fork (via Foundry):
- ERC-4626 auto-deposit: USDC native -> stata shares (Commit 2)
- Full-set mint through the CTF with stata as collateral (Commit 3)
- Inventory refresh pulls real balances; reconcile merges a full set back
  to stata (Commit 5)

All contract calls hit the fork for real. No Polymarket CLOB interaction —
these flows live purely on-chain and don't need the public order book.
"""

from cowdao_cowpy.common.chains import Chain
from web3 import Web3
from web3.types import RPCEndpoint

from prediction_market_agent_tooling.config import APIKeys
from prediction_market_agent_tooling.gtypes import (
    OutcomeWei,
    Wei,
    private_key_type,
    xDai,
)
from prediction_market_agent_tooling.markets.polymarket.api import (
    get_polymarkets_with_pagination,
)
from prediction_market_agent_tooling.markets.polymarket.inventory import (
    InventoryKey,
    PolymarketInventory,
)
from prediction_market_agent_tooling.markets.polymarket.polymarket_contracts import (
    PolymarketConditionalTokenContract,
    StataPolUSDCnContract,
    USDCContract,
)
from prediction_market_agent_tooling.tools.tokens.auto_deposit import (
    auto_deposit_collateral_token,
)
from prediction_market_agent_tooling.tools.utils import check_not_none
from tests_integration_with_local_chain.conftest import (
    create_and_fund_random_account,
    fund_account,
)

# Holds ~21M USDC native on Polygon mainnet (the Aave V3 aPolUSDCn reserve).
# Anvil's anvil_impersonateAccount bypasses any special transfer logic, so we
# can just call USDC.transfer from this account to fund a test EOA.
USDC_NATIVE_WHALE = Web3.to_checksum_address(
    "0xA4D94019934D8333Ef880ABFFbF2FDd611C762BD"
)


def _create_funded_account_usdc(
    polygon_local_web3: Web3, usdc_amount: float
) -> APIKeys:
    """Fresh EOA, POL for gas, USDC native stolen from a whale."""
    fresh_account = create_and_fund_random_account(
        web3=polygon_local_web3,
        deposit_amount=xDai(10),
    )
    api_keys = APIKeys(
        BET_FROM_PRIVATE_KEY=private_key_type(fresh_account.key.hex()),
        SAFE_ADDRESS=None,
    )
    # Steal USDC from a whale. The whale is a contract with no POL, so credit
    # it some gas, impersonate, then send a direct USDC.transfer via anvil.
    fund_account(
        polygon_local_web3,
        USDC_NATIVE_WHALE,
        xDai(100).as_xdai_wei.as_wei,
    )
    polygon_local_web3.provider.make_request(
        RPCEndpoint("anvil_impersonateAccount"), [USDC_NATIVE_WHALE]
    )
    usdc_wei = Wei(int(usdc_amount * 1e6))
    usdc = USDCContract()
    usdc_contract = polygon_local_web3.eth.contract(address=usdc.address, abi=usdc.abi)
    tx = usdc_contract.functions.transfer(
        api_keys.bet_from_address, usdc_wei.value
    ).build_transaction(
        {
            "from": USDC_NATIVE_WHALE,
            "nonce": polygon_local_web3.eth.get_transaction_count(USDC_NATIVE_WHALE),
        }
    )
    tx_hash = polygon_local_web3.eth.send_transaction(tx)
    polygon_local_web3.eth.wait_for_transaction_receipt(tx_hash)
    polygon_local_web3.provider.make_request(
        RPCEndpoint("anvil_stopImpersonatingAccount"), [USDC_NATIVE_WHALE]
    )
    return api_keys


def test_auto_deposit_usdc_native_to_stata(polygon_local_web3: Web3) -> None:
    """Commit 2: auto_deposit_collateral_token deposits USDC native into stata."""
    api_keys = _create_funded_account_usdc(polygon_local_web3, usdc_amount=20.0)
    stata = StataPolUSDCnContract()
    usdc = USDCContract()

    want_shares = Wei(int(10 * 1e6))
    auto_deposit_collateral_token(
        collateral_token_contract=stata,
        collateral_amount_wei_or_usd=want_shares,
        api_keys=api_keys,
        web3=polygon_local_web3,
        surplus=0,
        chain=Chain.POLYGON,
        keeping_erc20_token=usdc,
    )

    stata_balance = stata.balanceOf(api_keys.bet_from_address, web3=polygon_local_web3)
    # Shares >= requested shares (share-price is > 1 USDC since stata accrues yield)
    assert stata_balance.value >= want_shares.value
    # USDC native spent
    usdc_balance = usdc.balanceOf(api_keys.bet_from_address, web3=polygon_local_web3)
    assert usdc_balance.value < int(20 * 1e6)


def test_mint_full_set_with_stata(polygon_local_web3: Web3) -> None:
    """Commit 3: approve + splitPosition using stata as collateral produces a full set."""
    api_keys = _create_funded_account_usdc(polygon_local_web3, usdc_amount=20.0)
    stata = StataPolUSDCnContract()
    ctf = PolymarketConditionalTokenContract()

    # Mint stata shares first.
    want_shares = Wei(int(10 * 1e6))
    auto_deposit_collateral_token(
        collateral_token_contract=stata,
        collateral_amount_wei_or_usd=want_shares,
        api_keys=api_keys,
        web3=polygon_local_web3,
        surplus=0,
        chain=Chain.POLYGON,
        keeping_erc20_token=USDCContract(),
    )

    # Pick any live market's condition_id — the CTF creates a separate
    # (condition, stata) position set regardless of the market's own collateral.
    markets = check_not_none(
        get_polymarkets_with_pagination(closed=False, limit=1, only_binary=True)
    )
    market = check_not_none(markets[0].markets)[0]
    condition_id = market.conditionId

    stata_before = stata.balanceOf(api_keys.bet_from_address, web3=polygon_local_web3)
    mint_amount = Wei(int(5 * 1e6))
    ctf.mint_full_set(
        api_keys=api_keys,
        collateral_token=stata,
        condition_id=condition_id,
        amount=mint_amount,
        outcome_slot_count=2,
        web3=polygon_local_web3,
    )
    stata_after = stata.balanceOf(api_keys.bet_from_address, web3=polygon_local_web3)
    assert stata_before.value - stata_after.value == mint_amount.value

    # Both YES and NO positions sit at exactly `mint_amount`.
    inv = PolymarketInventory.empty()
    inv.add(InventoryKey(condition_id=condition_id, collateral_address=stata.address))
    snapshots = inv.refresh_from_chain(
        api_keys.bet_from_address, web3=polygon_local_web3
    )
    assert len(snapshots) == 1
    balances = [b.value for b in snapshots[0].balances_wei]
    assert balances == [mint_amount.value, mint_amount.value]


def test_inventory_reconcile_merges_full_set(polygon_local_web3: Web3) -> None:
    """Commit 5: reconcile_full_sets redeems balanced YES+NO back to collateral."""
    api_keys = _create_funded_account_usdc(polygon_local_web3, usdc_amount=20.0)
    stata = StataPolUSDCnContract()
    ctf = PolymarketConditionalTokenContract()

    want_shares = Wei(int(10 * 1e6))
    auto_deposit_collateral_token(
        collateral_token_contract=stata,
        collateral_amount_wei_or_usd=want_shares,
        api_keys=api_keys,
        web3=polygon_local_web3,
        surplus=0,
        chain=Chain.POLYGON,
        keeping_erc20_token=USDCContract(),
    )

    markets = check_not_none(
        get_polymarkets_with_pagination(closed=False, limit=1, only_binary=True)
    )
    condition_id = check_not_none(markets[0].markets)[0].conditionId

    mint_amount = Wei(int(3 * 1e6))
    ctf.mint_full_set(
        api_keys=api_keys,
        collateral_token=stata,
        condition_id=condition_id,
        amount=mint_amount,
        outcome_slot_count=2,
        web3=polygon_local_web3,
    )

    stata_after_mint = stata.balanceOf(
        api_keys.bet_from_address, web3=polygon_local_web3
    )

    inv = PolymarketInventory.empty()
    inv.add(InventoryKey(condition_id=condition_id, collateral_address=stata.address))
    post = inv.reconcile_full_sets(
        api_keys=api_keys,
        collateral_tokens={stata.address: stata},
        threshold=OutcomeWei(0),
        web3=polygon_local_web3,
    )

    # Every outcome leg zeroed out after the merge.
    assert [b.value for b in post[0].balances_wei] == [0, 0]

    # stata balance recovered by exactly the mint amount.
    stata_final = stata.balanceOf(api_keys.bet_from_address, web3=polygon_local_web3)
    assert stata_final.value - stata_after_mint.value == mint_amount.value
