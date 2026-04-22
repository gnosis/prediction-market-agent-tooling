"""Per-(condition, collateral) inventory tracking and full-set reconciliation.

Lets the agent hold YES/NO outcome tokens across multiple collaterals (e.g.
USDC.e and stataPolUSDCn) and redeem "balanced" pairs back to collateral by
calling `mergePositions` whenever `min(balance_yes, balance_no)` exceeds a
threshold. A balanced book carries no directional exposure, so redeeming it
frees capital with zero principal risk.
"""

import json
import typing as t
from pathlib import Path

from pydantic import BaseModel
from web3 import Web3

from prediction_market_agent_tooling.config import APIKeys
from prediction_market_agent_tooling.gtypes import ChecksumAddress, HexBytes, OutcomeWei
from prediction_market_agent_tooling.loggers import logger
from prediction_market_agent_tooling.markets.polymarket.polymarket_contracts import (
    PolymarketConditionalTokenContract,
)
from prediction_market_agent_tooling.tools.contract import ContractERC20BaseClass


class InventoryKey(BaseModel):
    """Identifies one (market, collateral) slice of inventory."""

    condition_id: HexBytes
    collateral_address: ChecksumAddress
    outcome_slot_count: int = 2

    model_config = {"frozen": True}

    def __hash__(self) -> int:
        return hash((bytes(self.condition_id), self.collateral_address))


class InventoryBalances(BaseModel):
    """On-chain balances for each outcome of an InventoryKey."""

    key: InventoryKey
    balances_wei: list[OutcomeWei]

    @property
    def redeemable_full_sets(self) -> OutcomeWei:
        """Full sets we could merge back to collateral right now."""
        if not self.balances_wei:
            return OutcomeWei(0)
        return OutcomeWei(min(b.value for b in self.balances_wei))


class PolymarketInventory(BaseModel):
    """Collection of (condition, collateral) slices we care about.

    State is the *set of keys we track*; the actual balances are always
    read fresh from chain via `refresh_from_chain`.
    """

    keys: list[InventoryKey]

    def add(self, key: InventoryKey) -> None:
        if key not in self.keys:
            self.keys.append(key)

    def save(self, path: str | Path) -> None:
        data = self.model_dump(mode="json")
        with open(path, "w") as f:
            json.dump(data, f, indent=2)

    @staticmethod
    def load(path: str | Path) -> "PolymarketInventory":
        with open(path) as f:
            data = json.load(f)
        return PolymarketInventory.model_validate(data)

    @staticmethod
    def empty() -> "PolymarketInventory":
        return PolymarketInventory(keys=[])

    def refresh_from_chain(
        self,
        owner: ChecksumAddress,
        web3: Web3 | None = None,
    ) -> list[InventoryBalances]:
        ctf = PolymarketConditionalTokenContract()
        out: list[InventoryBalances] = []
        for key in self.keys:
            balances = _balances_for_key(ctf, owner, key, web3)
            out.append(InventoryBalances(key=key, balances_wei=balances))
        return out

    def reconcile_full_sets(
        self,
        api_keys: APIKeys,
        collateral_tokens: dict[ChecksumAddress, ContractERC20BaseClass],
        threshold: OutcomeWei = OutcomeWei(0),
        web3: Web3 | None = None,
    ) -> list[InventoryBalances]:
        """For each tracked key, merge any full set we can down to collateral.

        Caller provides a map from collateral_address → ERC20 wrapper so we can
        reuse typed contract classes (e.g. USDCeContract, StataPolUSDCnContract).
        Returns the post-merge balance snapshot.
        """
        ctf = PolymarketConditionalTokenContract()
        owner = api_keys.bet_from_address
        snapshots = self.refresh_from_chain(owner, web3)

        for snap in snapshots:
            redeemable = snap.redeemable_full_sets
            if redeemable.value <= threshold.value:
                continue
            collateral = collateral_tokens.get(snap.key.collateral_address)
            if collateral is None:
                logger.warning(
                    f"Skipping reconcile for {snap.key.condition_id.to_0x_hex()}: "
                    f"no collateral wrapper registered for {snap.key.collateral_address}"
                )
                continue
            logger.info(
                f"Merging {redeemable} full sets of "
                f"{snap.key.condition_id.to_0x_hex()} back to "
                f"{collateral.symbol(web3=web3)}"
            )
            ctf.merge_full_set(
                api_keys=api_keys,
                collateral_token=collateral,
                condition_id=snap.key.condition_id,
                amount=redeemable,
                outcome_slot_count=snap.key.outcome_slot_count,
                web3=web3,
            )

        return self.refresh_from_chain(owner, web3)


def _balances_for_key(
    ctf: PolymarketConditionalTokenContract,
    owner: ChecksumAddress,
    key: InventoryKey,
    web3: Web3 | None,
) -> list[OutcomeWei]:
    balances: list[OutcomeWei] = []
    for i in range(key.outcome_slot_count):
        index_set = 1 << i
        collection_id = ctf.getCollectionId(
            parent_collection_id=HexBytes(b"\x00" * 32),
            condition_id=key.condition_id,
            index_set=index_set,
            web3=web3,
        )
        position_id = ctf.getPositionId(
            collateral_token_address=key.collateral_address,
            collection_id=collection_id,
            web3=web3,
        )
        balances.append(
            ctf.balanceOf(from_address=owner, position_id=position_id, web3=web3)
        )
    return balances


# Re-export the tuple type for tests / callers.
__all__: t.Final[list[str]] = [
    "InventoryBalances",
    "InventoryKey",
    "PolymarketInventory",
]
