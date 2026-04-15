import tempfile
from pathlib import Path

from web3 import Web3

from prediction_market_agent_tooling.gtypes import HexBytes, OutcomeWei
from prediction_market_agent_tooling.markets.polymarket.inventory import (
    InventoryBalances,
    InventoryKey,
    PolymarketInventory,
)

USDC_E = Web3.to_checksum_address("0x2791Bca1f2de4661ED88A30C99A7a9449Aa84174")
STATA = Web3.to_checksum_address("0x2DCA80061632f3F87c9cA28364d1d0c30cD79a19")
COND_A = HexBytes(b"\xaa" * 32)
COND_B = HexBytes(b"\xbb" * 32)


def test_redeemable_is_min_of_balances() -> None:
    key = InventoryKey(condition_id=COND_A, collateral_address=USDC_E)
    bal = InventoryBalances(key=key, balances_wei=[OutcomeWei(100), OutcomeWei(60)])
    assert bal.redeemable_full_sets == OutcomeWei(60)


def test_redeemable_empty_is_zero() -> None:
    key = InventoryKey(condition_id=COND_A, collateral_address=USDC_E)
    bal = InventoryBalances(key=key, balances_wei=[])
    assert bal.redeemable_full_sets == OutcomeWei(0)


def test_redeemable_one_zero_side() -> None:
    key = InventoryKey(condition_id=COND_A, collateral_address=USDC_E)
    bal = InventoryBalances(key=key, balances_wei=[OutcomeWei(500), OutcomeWei(0)])
    # fully one-sided book: nothing to redeem without taking directional risk
    assert bal.redeemable_full_sets == OutcomeWei(0)


def test_inventory_add_dedup() -> None:
    inv = PolymarketInventory.empty()
    k1 = InventoryKey(condition_id=COND_A, collateral_address=USDC_E)
    k2 = InventoryKey(condition_id=COND_A, collateral_address=USDC_E)
    inv.add(k1)
    inv.add(k2)
    assert len(inv.keys) == 1


def test_inventory_add_distinct_keys() -> None:
    inv = PolymarketInventory.empty()
    inv.add(InventoryKey(condition_id=COND_A, collateral_address=USDC_E))
    inv.add(InventoryKey(condition_id=COND_A, collateral_address=STATA))
    inv.add(InventoryKey(condition_id=COND_B, collateral_address=USDC_E))
    assert len(inv.keys) == 3


def test_inventory_roundtrip_persist() -> None:
    inv = PolymarketInventory.empty()
    inv.add(InventoryKey(condition_id=COND_A, collateral_address=USDC_E))
    inv.add(InventoryKey(condition_id=COND_B, collateral_address=STATA))

    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "inv.json"
        inv.save(path)
        loaded = PolymarketInventory.load(path)

    assert len(loaded.keys) == 2
    # HexBytes equality is by underlying bytes
    assert loaded.keys[0].condition_id == COND_A
    assert loaded.keys[1].collateral_address == STATA
