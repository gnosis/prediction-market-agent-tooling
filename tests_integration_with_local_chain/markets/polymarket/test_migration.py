"""Integration tests for atomic USDC.e -> stata position migration.

All tests run against a live anvil Polygon fork (via the `polygon_local_web3`
fixture). Real CTF, real stataPolUSDCn vault, real USDC and USDC.e tokens
obtained by impersonating on-chain whales.
"""

from unittest import mock

import pytest
from eth_account.signers.local import LocalAccount
from eth_typing import URI
from safe_eth.eth import EthereumClient
from web3 import Web3
from web3.types import RPCEndpoint

from prediction_market_agent_tooling.config import APIKeys
from prediction_market_agent_tooling.gtypes import (
    ABI,
    ChecksumAddress,
    HexBytes,
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
from prediction_market_agent_tooling.markets.polymarket.migration import (
    migrate_from_inventory,
    migrate_position,
    migrate_via_fresh_mint,
)
from prediction_market_agent_tooling.markets.polymarket.polymarket_contracts import (
    PolymarketConditionalTokenContract,
    StataPolUSDCnContract,
    USDCContract,
    USDCeContract,
)
from prediction_market_agent_tooling.tools.safe import create_safe
from prediction_market_agent_tooling.tools.utils import check_not_none
from prediction_market_agent_tooling.tools.web3_utils import send_safe_batch_tx
from tests_integration_with_local_chain.conftest import (
    create_and_fund_random_account,
    fund_account,
)

USDC_NATIVE_WHALE = Web3.to_checksum_address(
    "0xA4D94019934D8333Ef880ABFFbF2FDd611C762BD"
)
USDCE_WHALE = Web3.to_checksum_address("0x5a58505a96D1dbf8dF91cB21B54419FC36e93fdE")


def _impersonate_erc20_transfer(
    web3: Web3,
    whale: ChecksumAddress,
    token_address: ChecksumAddress,
    token_abi: ABI,
    to: ChecksumAddress,
    amount_wei: int,
) -> None:
    fund_account(web3, whale, xDai(100).as_xdai_wei.as_wei)
    web3.provider.make_request(RPCEndpoint("anvil_impersonateAccount"), [whale])
    token_contract = web3.eth.contract(address=token_address, abi=token_abi)
    tx = token_contract.functions.transfer(to, amount_wei).build_transaction(
        {"from": whale, "nonce": web3.eth.get_transaction_count(whale)}
    )
    tx_hash = web3.eth.send_transaction(tx)
    web3.eth.wait_for_transaction_receipt(tx_hash)
    web3.provider.make_request(RPCEndpoint("anvil_stopImpersonatingAccount"), [whale])


def _create_user_with_usdce_full_set(
    polygon_local_web3: Web3,
    safe_address: ChecksumAddress,
    usdc_e_amount_micro: int,
    condition_id: HexBytes,
    approve_safe: bool = True,
) -> APIKeys:
    """Fresh user EOA holding a minted USDC.e full set for `condition_id`.

    Returns the user's APIKeys (EOA, no Safe). The user has already called
    `setApprovalForAll(safe_address, True)` so the migration batch can pull
    their ERC1155s.
    """
    user_account = create_and_fund_random_account(
        web3=polygon_local_web3, deposit_amount=xDai(10)
    )
    user_keys = APIKeys(
        BET_FROM_PRIVATE_KEY=private_key_type(user_account.key.hex()),
        SAFE_ADDRESS=None,
    )
    usdce = USDCeContract()
    _impersonate_erc20_transfer(
        polygon_local_web3,
        USDCE_WHALE,
        usdce.address,
        usdce.abi,
        user_keys.bet_from_address,
        usdc_e_amount_micro,
    )
    ctf = PolymarketConditionalTokenContract()
    ctf.mint_full_set(
        api_keys=user_keys,
        collateral_token=usdce,
        condition_id=condition_id,
        amount=Wei(usdc_e_amount_micro),
        outcome_slot_count=2,
        web3=polygon_local_web3,
    )
    if approve_safe:
        ctf.setApprovalForAll(
            api_keys=user_keys,
            for_address=safe_address,
            approve=True,
            web3=polygon_local_web3,
        )
    return user_keys


def _deploy_funded_safe(polygon_local_web3: Web3, stata_amount_micro: int) -> APIKeys:
    """Deploy a Safe on the Polygon fork with `stata_amount_micro` stata inside.

    The operator EOA (owner) is a fresh random account funded with POL for
    gas. USDC native is impersonated from a whale into the Safe, then wrapped
    to stata via `auto_deposit_collateral_token`.
    """
    owner_account: LocalAccount = create_and_fund_random_account(
        web3=polygon_local_web3, deposit_amount=xDai(10)
    )
    ethereum_client = EthereumClient(URI(polygon_local_web3.provider.endpoint_uri))  # type: ignore
    safe_address = create_safe(
        ethereum_client=ethereum_client,
        account=owner_account,
        owners=[owner_account.address],
        salt_nonce=42,
        threshold=1,
    )
    assert safe_address is not None

    safe_keys = APIKeys(
        BET_FROM_PRIVATE_KEY=private_key_type(owner_account.key.hex()),
        SAFE_ADDRESS=str(safe_address),
    )

    usdc = USDCContract()
    # Over-fund USDC a bit; ERC-4626 round-trip can cost 1-2 wei.
    usdc_seed_micro = stata_amount_micro + 10
    _impersonate_erc20_transfer(
        polygon_local_web3,
        USDC_NATIVE_WHALE,
        usdc.address,
        usdc.abi,
        Web3.to_checksum_address(safe_address),
        usdc_seed_micro,
    )
    # Wrap Safe's USDC native -> stata shares. We wrap the full USDC balance
    # to guarantee >= stata_amount_micro shares after ERC-4626 rounding.
    stata = StataPolUSDCnContract()
    stata.deposit_asset_token(
        asset_value=Wei(usdc_seed_micro),
        api_keys=safe_keys,
        web3=polygon_local_web3,
    )
    return safe_keys


def _pick_open_condition_id() -> HexBytes:
    markets = check_not_none(
        get_polymarkets_with_pagination(closed=False, limit=1, only_binary=True)
    )
    return check_not_none(markets[0].markets)[0].conditionId


def _read_outcome_balances(
    web3: Web3,
    owner: ChecksumAddress,
    condition_id: HexBytes,
    collateral_address: ChecksumAddress,
) -> tuple[OutcomeWei, OutcomeWei]:
    ctf = PolymarketConditionalTokenContract()
    yes_id = ctf._position_id_for(collateral_address, condition_id, 1, web3=web3)
    no_id = ctf._position_id_for(collateral_address, condition_id, 2, web3=web3)
    yes_bal = ctf.balanceOf(from_address=owner, position_id=yes_id, web3=web3)
    no_bal = ctf.balanceOf(from_address=owner, position_id=no_id, web3=web3)
    return yes_bal, no_bal


def test_migrate_via_fresh_mint_transfers_stata_yes_and_pulls_usdce_yes(
    polygon_local_web3: Web3,
) -> None:
    condition_id = _pick_open_condition_id()
    amount = OutcomeWei(int(3 * 1e6))

    safe_keys = _deploy_funded_safe(polygon_local_web3, stata_amount_micro=int(5 * 1e6))
    safe_address = check_not_none(safe_keys.safe_address_checksum)
    user_keys = _create_user_with_usdce_full_set(
        polygon_local_web3,
        safe_address=safe_address,
        usdc_e_amount_micro=int(5 * 1e6),
        condition_id=condition_id,
    )

    stata = StataPolUSDCnContract()
    stata_before = stata.balanceOf(for_address=safe_address, web3=polygon_local_web3)

    inventory = PolymarketInventory.empty()
    result = migrate_via_fresh_mint(
        api_keys=safe_keys,
        inventory=inventory,
        condition_id=condition_id,
        user_address=user_keys.bet_from_address,
        amount=amount,
        outcome_index=0,
        outcome_slot_count=2,
        web3=polygon_local_web3,
    )

    assert result.source == "fresh_mint"
    assert result.amount_in_wei == amount
    assert result.amount_out_wei == amount  # one_to_one
    assert result.leftover_no_wei == amount

    # Safe spent `amount` stata to mint the full set.
    stata_after = stata.balanceOf(for_address=safe_address, web3=polygon_local_web3)
    assert stata_before.value - stata_after.value == amount.value

    # User lost all their USDC.e-YES, gained `amount` stata-YES, still has NO.
    user_usdce_yes, user_usdce_no = _read_outcome_balances(
        polygon_local_web3,
        user_keys.bet_from_address,
        condition_id,
        USDCeContract().address,
    )
    user_stata_yes, user_stata_no = _read_outcome_balances(
        polygon_local_web3,
        user_keys.bet_from_address,
        condition_id,
        stata.address,
    )
    assert user_usdce_yes.value == int(5 * 1e6) - amount.value
    assert user_usdce_no.value == int(5 * 1e6)
    assert user_stata_yes.value == amount.value
    assert user_stata_no.value == 0

    # Safe holds the pulled USDC.e-YES plus freshly-minted stata-NO.
    safe_usdce_yes, _ = _read_outcome_balances(
        polygon_local_web3,
        safe_address,
        condition_id,
        USDCeContract().address,
    )
    _, safe_stata_no = _read_outcome_balances(
        polygon_local_web3,
        safe_address,
        condition_id,
        stata.address,
    )
    assert safe_usdce_yes.value == amount.value
    assert safe_stata_no.value == amount.value

    # Inventory keys for both collaterals registered.
    assert len(inventory.keys) == 2
    assert {k.collateral_address for k in inventory.keys} == {
        USDCeContract().address,
        stata.address,
    }


def test_migrate_from_inventory_skips_mint_legs(polygon_local_web3: Web3) -> None:
    condition_id = _pick_open_condition_id()
    amount = OutcomeWei(int(2 * 1e6))
    inv_seed = int(4 * 1e6)

    safe_keys = _deploy_funded_safe(polygon_local_web3, stata_amount_micro=int(6 * 1e6))
    safe_address = check_not_none(safe_keys.safe_address_checksum)

    # Pre-seed Safe with a stata full set so inventory path has stock.
    ctf = PolymarketConditionalTokenContract()
    ctf.mint_full_set_via_safe_batch(
        api_keys=safe_keys,
        collateral_token=StataPolUSDCnContract(),
        condition_id=condition_id,
        amount=Wei(inv_seed),
        outcome_slot_count=2,
        web3=polygon_local_web3,
    )
    stata = StataPolUSDCnContract()
    stata_before = stata.balanceOf(for_address=safe_address, web3=polygon_local_web3)

    user_keys = _create_user_with_usdce_full_set(
        polygon_local_web3,
        safe_address=safe_address,
        usdc_e_amount_micro=int(5 * 1e6),
        condition_id=condition_id,
    )

    inventory = PolymarketInventory.empty()
    result = migrate_from_inventory(
        api_keys=safe_keys,
        inventory=inventory,
        condition_id=condition_id,
        user_address=user_keys.bet_from_address,
        amount=amount,
        outcome_index=0,
        outcome_slot_count=2,
        web3=polygon_local_web3,
    )

    assert result.source == "inventory"
    assert result.amount_in_wei == amount
    assert result.amount_out_wei == amount
    assert result.leftover_no_wei == OutcomeWei(0)

    # Safe stata balance unchanged — no split-position leg.
    stata_after = stata.balanceOf(for_address=safe_address, web3=polygon_local_web3)
    assert stata_after.value == stata_before.value

    # Safe's stata-YES dropped by `amount`; stata-NO unchanged.
    safe_stata_yes, safe_stata_no = _read_outcome_balances(
        polygon_local_web3, safe_address, condition_id, stata.address
    )
    assert safe_stata_yes.value == inv_seed - amount.value
    assert safe_stata_no.value == inv_seed

    # User received stata-YES.
    user_stata_yes, _ = _read_outcome_balances(
        polygon_local_web3,
        user_keys.bet_from_address,
        condition_id,
        stata.address,
    )
    assert user_stata_yes.value == amount.value


def test_migrate_dispatch_picks_inventory_when_balance_sufficient(
    polygon_local_web3: Web3,
) -> None:
    condition_id = _pick_open_condition_id()
    amount = OutcomeWei(int(1 * 1e6))

    safe_keys = _deploy_funded_safe(polygon_local_web3, stata_amount_micro=int(6 * 1e6))
    safe_address = check_not_none(safe_keys.safe_address_checksum)

    ctf = PolymarketConditionalTokenContract()
    ctf.mint_full_set_via_safe_batch(
        api_keys=safe_keys,
        collateral_token=StataPolUSDCnContract(),
        condition_id=condition_id,
        amount=Wei(int(4 * 1e6)),
        outcome_slot_count=2,
        web3=polygon_local_web3,
    )

    user_keys = _create_user_with_usdce_full_set(
        polygon_local_web3,
        safe_address=safe_address,
        usdc_e_amount_micro=int(3 * 1e6),
        condition_id=condition_id,
    )

    result = migrate_position(
        api_keys=safe_keys,
        inventory=PolymarketInventory.empty(),
        condition_id=condition_id,
        user_address=user_keys.bet_from_address,
        amount=amount,
        outcome_index=0,
        outcome_slot_count=2,
        web3=polygon_local_web3,
    )
    assert result.source == "inventory"


def test_migrate_reverts_if_user_did_not_approve_safe(
    polygon_local_web3: Web3,
) -> None:
    condition_id = _pick_open_condition_id()
    amount = OutcomeWei(int(1 * 1e6))

    safe_keys = _deploy_funded_safe(polygon_local_web3, stata_amount_micro=int(3 * 1e6))
    safe_address = check_not_none(safe_keys.safe_address_checksum)
    user_keys = _create_user_with_usdce_full_set(
        polygon_local_web3,
        safe_address=safe_address,
        usdc_e_amount_micro=int(3 * 1e6),
        condition_id=condition_id,
        approve_safe=False,
    )

    with pytest.raises(ValueError, match="setApprovalForAll"):
        migrate_via_fresh_mint(
            api_keys=safe_keys,
            inventory=PolymarketInventory.empty(),
            condition_id=condition_id,
            user_address=user_keys.bet_from_address,
            amount=amount,
            web3=polygon_local_web3,
        )


def test_migrate_reverts_if_condition_resolved(polygon_local_web3: Web3) -> None:
    condition_id = _pick_open_condition_id()
    amount = OutcomeWei(int(1 * 1e6))

    safe_keys = _deploy_funded_safe(polygon_local_web3, stata_amount_micro=int(3 * 1e6))
    safe_address = check_not_none(safe_keys.safe_address_checksum)
    user_keys = _create_user_with_usdce_full_set(
        polygon_local_web3,
        safe_address=safe_address,
        usdc_e_amount_micro=int(3 * 1e6),
        condition_id=condition_id,
    )

    # Simulate a resolved condition by patching the wrapper; cheap compared to
    # impersonating UMA adapters to call reportPayouts on-chain, and it
    # targets the precheck we actually want to verify.
    with mock.patch.object(
        PolymarketConditionalTokenContract,
        "is_condition_resolved",
        return_value=True,
    ):
        with pytest.raises(ValueError, match="already resolved"):
            migrate_via_fresh_mint(
                api_keys=safe_keys,
                inventory=PolymarketInventory.empty(),
                condition_id=condition_id,
                user_address=user_keys.bet_from_address,
                amount=amount,
                web3=polygon_local_web3,
            )


def test_migrate_auto_reconcile_merges_matched_sets(
    polygon_local_web3: Web3,
) -> None:
    """After migration, Safe holds USDC.e-YES + can be seeded with USDC.e-NO.

    auto_reconcile=True should then merge the matched pair back to USDC.e.
    """
    condition_id = _pick_open_condition_id()
    amount = OutcomeWei(int(2 * 1e6))

    safe_keys = _deploy_funded_safe(polygon_local_web3, stata_amount_micro=int(4 * 1e6))
    safe_address = check_not_none(safe_keys.safe_address_checksum)

    # Pre-seed Safe with USDC.e-NO so that after migration's pull of
    # USDC.e-YES, reconcile_full_sets can merge the pair back to USDC.e.
    usdce = USDCeContract()
    _impersonate_erc20_transfer(
        polygon_local_web3,
        USDCE_WHALE,
        usdce.address,
        usdce.abi,
        safe_address,
        amount.value,
    )
    ctf = PolymarketConditionalTokenContract()
    ctf.mint_full_set_via_safe_batch(
        api_keys=safe_keys,
        collateral_token=usdce,
        condition_id=condition_id,
        amount=Wei(amount.value),
        outcome_slot_count=2,
        web3=polygon_local_web3,
    )
    # Safe now has USDC.e-YES (amount) + USDC.e-NO (amount). Move the YES
    # elsewhere so the pre-reconcile Safe has only USDC.e-NO.
    seed_yes_id = ctf._position_id_for(
        usdce.address, condition_id, 1, web3=polygon_local_web3
    )
    sink = create_and_fund_random_account(
        web3=polygon_local_web3, deposit_amount=xDai(1)
    )
    transfer_call = ctf._erc1155_transfer_call(
        polygon_local_web3,
        safe_address,
        Web3.to_checksum_address(sink.address),
        seed_yes_id,
        amount,
    )
    send_safe_batch_tx(
        web3=polygon_local_web3,
        safe_address=safe_address,
        from_private_key=safe_keys.bet_from_private_key,
        calls=[transfer_call],
    )

    usdce_before = usdce.balanceOf(for_address=safe_address, web3=polygon_local_web3)

    user_keys = _create_user_with_usdce_full_set(
        polygon_local_web3,
        safe_address=safe_address,
        usdc_e_amount_micro=int(3 * 1e6),
        condition_id=condition_id,
    )

    inventory = PolymarketInventory(
        keys=[
            InventoryKey(condition_id=condition_id, collateral_address=usdce.address),
            InventoryKey(
                condition_id=condition_id,
                collateral_address=StataPolUSDCnContract().address,
            ),
        ]
    )
    migrate_position(
        api_keys=safe_keys,
        inventory=inventory,
        condition_id=condition_id,
        user_address=user_keys.bet_from_address,
        amount=amount,
        outcome_index=0,
        outcome_slot_count=2,
        auto_reconcile=True,
        web3=polygon_local_web3,
    )

    # Reconcile should have merged `amount` of USDC.e-YES + USDC.e-NO back to
    # USDC.e collateral.
    usdce_after = usdce.balanceOf(for_address=safe_address, web3=polygon_local_web3)
    assert usdce_after.value - usdce_before.value == amount.value

    safe_usdce_yes, safe_usdce_no = _read_outcome_balances(
        polygon_local_web3, safe_address, condition_id, usdce.address
    )
    assert safe_usdce_yes.value == 0
    assert safe_usdce_no.value == 0
