"""Atomic 1:1 position migration (USDC.e → stata) for Polymarket.

Demo flow: a Polymarket user holding N USDC.e-backed outcome ERC1155s swaps
them 1:1 for stata-backed outcome ERC1155s on the same condition, in one
Safe MultiSend transaction. After the swap the operator Safe is long
USDC.e-<chosen outcome> (user's old tokens) and, when minting was required,
long stata-<other outcome(s)> (leftover from the fresh split).

Prerequisite for the user: a one-time
`ctf.setApprovalForAll(safe_address, True)` so the batch can pull their
ERC1155s. The Safe transfers its own tokens out — that leg needs no
approval plumbing.
"""

from dataclasses import dataclass
from typing import Literal

from web3 import Web3
from web3.types import TxReceipt

from prediction_market_agent_tooling.config import APIKeys
from prediction_market_agent_tooling.gtypes import (
    ChecksumAddress,
    HexBytes,
    OutcomeWei,
    Wei,
)
from prediction_market_agent_tooling.loggers import logger
from prediction_market_agent_tooling.markets.polymarket.inventory import (
    InventoryKey,
    PolymarketInventory,
)
from prediction_market_agent_tooling.markets.polymarket.polymarket_contracts import (
    PolymarketConditionalTokenContract,
    StataPolUSDCnContract,
    USDCeContract,
    Wrapped1155Contract,
    Wrapped1155FactoryContract,
)
from prediction_market_agent_tooling.tools.web3_utils import (
    SafeBatchCall,
    encode_contract_call,
    send_safe_batch_tx,
)

ExchangeRate = Literal["one_to_one", "erc4626_shares"]
MigrationSource = Literal["inventory", "fresh_mint"]


@dataclass(frozen=True)
class MigrationResult:
    receipt: TxReceipt
    source: MigrationSource
    amount_in_wei: OutcomeWei
    amount_out_wei: OutcomeWei
    leftover_no_wei: OutcomeWei
    wrapped_erc20_address: ChecksumAddress | None = None


def _default_wrap_metadata(
    condition_id: HexBytes, outcome_index: int
) -> tuple[str, str, int]:
    """Derive ERC-20 name/symbol for the wrapped outcome token.

    Short-string form caps at 31 bytes — we use the leading 6 hex chars of
    the condition id to keep the symbol human-recognisable without blowing
    the limit.
    """
    outcome = "YES" if outcome_index == 0 else f"OUT{outcome_index}"
    cond_prefix = condition_id.to_0x_hex()[2:10]
    return (
        f"wstata-{outcome}-{cond_prefix}",
        f"wS{outcome}-{cond_prefix}",
        6,
    )


def _resolve_amount_out(
    amount_in: OutcomeWei,
    exchange_rate: ExchangeRate,
    stata: StataPolUSDCnContract,
    web3: Web3 | None,
) -> OutcomeWei:
    if exchange_rate == "one_to_one":
        return amount_in
    shares = stata.convertToShares(Wei(amount_in.value), web3=web3)
    if shares.value <= 0:
        raise ValueError(
            f"ERC-4626 convertToShares returned {shares} for {amount_in}; "
            "vault looks uninitialised."
        )
    return OutcomeWei(shares.value)


def _precheck(
    ctf: PolymarketConditionalTokenContract,
    safe_address: ChecksumAddress,
    condition_id: HexBytes,
    user_address: ChecksumAddress,
    source_position_id: int,
    amount_in: OutcomeWei,
    web3: Web3 | None,
) -> None:
    if ctf.is_condition_resolved(condition_id=condition_id, web3=web3):
        raise ValueError(
            f"Condition {condition_id.to_0x_hex()} already resolved; "
            "migration is only for live markets."
        )
    if not ctf.isApprovedForAll(
        owner=user_address, for_address=safe_address, web3=web3
    ):
        raise ValueError(
            f"User {user_address} must call "
            f"`setApprovalForAll({safe_address}, True)` on the CTF before migration."
        )
    user_balance = ctf.balanceOf(
        from_address=user_address, position_id=source_position_id, web3=web3
    )
    if user_balance.value < amount_in.value:
        raise ValueError(
            f"User holds {user_balance} of source outcome; requested {amount_in}."
        )


def _final_push_legs(
    web3: Web3,
    ctf: PolymarketConditionalTokenContract,
    safe_address: ChecksumAddress,
    user_address: ChecksumAddress,
    target_position_id: int,
    amount_out: OutcomeWei,
    wrap_metadata: bytes | None,
) -> list[SafeBatchCall]:
    """Either push raw ERC-1155 to user, or route via factory to produce ERC-20.

    `wrap_metadata is None` → single leg, raw ERC-1155 to user.
    `wrap_metadata is not None` → two legs, factory wraps then Safe transfers
    the freshly-minted ERC-20 to the user.
    """
    if wrap_metadata is None:
        return [
            ctf._erc1155_transfer_call(
                web3, safe_address, user_address, target_position_id, amount_out
            )
        ]
    factory = Wrapped1155FactoryContract()
    wrapped_address = factory.get_wrapped_1155(
        multi_token=ctf.address,
        token_id=target_position_id,
        data=wrap_metadata,
        web3=web3,
    )
    wrapped_erc20 = Wrapped1155Contract(address=wrapped_address)
    return [
        # Safe hands ERC-1155 to the factory with the metadata payload;
        # factory CREATE2-deploys the ERC-20 if needed and mints to Safe.
        ctf._erc1155_transfer_call(
            web3,
            safe_address,
            factory.address,
            target_position_id,
            amount_out,
            wrap_metadata,
        ),
        encode_contract_call(
            web3=web3,
            contract_address=wrapped_erc20.address,
            contract_abi=wrapped_erc20.abi,
            function_name="transfer",
            function_params=[user_address, amount_out.value],
        ),
    ]


def _build_inventory_calls(
    web3: Web3,
    ctf: PolymarketConditionalTokenContract,
    safe_address: ChecksumAddress,
    user_address: ChecksumAddress,
    source_position_id: int,
    target_position_id: int,
    amount_in: OutcomeWei,
    amount_out: OutcomeWei,
    wrap_metadata: bytes | None,
) -> list[SafeBatchCall]:
    return [
        ctf._erc1155_transfer_call(
            web3, user_address, safe_address, source_position_id, amount_in
        ),
        *_final_push_legs(
            web3,
            ctf,
            safe_address,
            user_address,
            target_position_id,
            amount_out,
            wrap_metadata,
        ),
    ]


def _build_fresh_mint_calls(
    web3: Web3,
    ctf: PolymarketConditionalTokenContract,
    target_collateral: StataPolUSDCnContract,
    safe_address: ChecksumAddress,
    user_address: ChecksumAddress,
    condition_id: HexBytes,
    source_position_id: int,
    target_position_id: int,
    amount_in: OutcomeWei,
    amount_out: OutcomeWei,
    outcome_slot_count: int,
    wrap_metadata: bytes | None,
) -> list[SafeBatchCall]:
    split_amount = Wei(amount_out.value)
    return [
        ctf._collateral_approve_call(
            web3, target_collateral, ctf.address, split_amount
        ),
        ctf._split_position_call(
            web3, target_collateral, condition_id, outcome_slot_count, split_amount
        ),
        ctf._erc1155_transfer_call(
            web3, user_address, safe_address, source_position_id, amount_in
        ),
        *_final_push_legs(
            web3,
            ctf,
            safe_address,
            user_address,
            target_position_id,
            amount_out,
            wrap_metadata,
        ),
    ]


def _register_inventory_keys(
    inventory: PolymarketInventory,
    condition_id: HexBytes,
    outcome_slot_count: int,
    usdce: USDCeContract,
    stata: StataPolUSDCnContract,
) -> None:
    inventory.add(
        InventoryKey(
            condition_id=condition_id,
            collateral_address=usdce.address,
            outcome_slot_count=outcome_slot_count,
        )
    )
    inventory.add(
        InventoryKey(
            condition_id=condition_id,
            collateral_address=stata.address,
            outcome_slot_count=outcome_slot_count,
        )
    )


def migrate_from_inventory(
    api_keys: APIKeys,
    inventory: PolymarketInventory,
    condition_id: HexBytes,
    user_address: ChecksumAddress,
    amount: OutcomeWei,
    outcome_index: int = 0,
    outcome_slot_count: int = 2,
    exchange_rate: ExchangeRate = "one_to_one",
    wrap_output: bool = False,
    web3: Web3 | None = None,
) -> MigrationResult:
    """Swap using stata outcome tokens already held by the Safe.

    No mint leg in the batch — only two ERC1155 transfers (or three legs
    when `wrap_output=True`: ERC1155 pull + wrap + ERC20 transfer). Reverts
    if the Safe does not already hold at least `amount_out` stata-<outcome>.
    """
    safe_address = api_keys.safe_address_checksum
    if safe_address is None:
        raise ValueError("migrate_from_inventory requires SAFE_ADDRESS.")

    ctf = PolymarketConditionalTokenContract()
    usdce = USDCeContract()
    stata = StataPolUSDCnContract()
    index_set = 1 << outcome_index

    source_position_id = ctf._position_id_for(
        usdce.address, condition_id, index_set, web3=web3
    )
    target_position_id = ctf._position_id_for(
        stata.address, condition_id, index_set, web3=web3
    )

    _precheck(
        ctf=ctf,
        safe_address=safe_address,
        condition_id=condition_id,
        user_address=user_address,
        source_position_id=source_position_id,
        amount_in=amount,
        web3=web3,
    )

    amount_out = _resolve_amount_out(amount, exchange_rate, stata, web3)
    safe_target_balance = ctf.balanceOf(
        from_address=safe_address, position_id=target_position_id, web3=web3
    )
    if safe_target_balance.value < amount_out.value:
        raise ValueError(
            f"Safe holds {safe_target_balance} of stata-<outcome>; "
            f"need {amount_out}. Use migrate_via_fresh_mint instead."
        )

    w3 = web3 or ctf.get_web3()
    wrap_metadata: bytes | None = None
    wrapped_erc20_address: ChecksumAddress | None = None
    if wrap_output:
        name, symbol, decimals = _default_wrap_metadata(condition_id, outcome_index)
        wrap_metadata = Wrapped1155FactoryContract.encode_metadata(
            name, symbol, decimals
        )
        wrapped_erc20_address = Wrapped1155FactoryContract().get_wrapped_1155(
            multi_token=ctf.address,
            token_id=target_position_id,
            data=wrap_metadata,
            web3=w3,
        )

    calls = _build_inventory_calls(
        web3=w3,
        ctf=ctf,
        safe_address=safe_address,
        user_address=user_address,
        source_position_id=source_position_id,
        target_position_id=target_position_id,
        amount_in=amount,
        amount_out=amount_out,
        wrap_metadata=wrap_metadata,
    )
    logger.info(
        f"Migration path=inventory condition={condition_id.to_0x_hex()} "
        f"user={user_address} amount_in={amount} amount_out={amount_out} "
        f"wrap_output={wrap_output}"
    )
    receipt = send_safe_batch_tx(
        web3=w3,
        safe_address=safe_address,
        from_private_key=api_keys.bet_from_private_key,
        calls=calls,
    )
    _register_inventory_keys(inventory, condition_id, outcome_slot_count, usdce, stata)
    return MigrationResult(
        receipt=receipt,
        source="inventory",
        amount_in_wei=amount,
        amount_out_wei=amount_out,
        leftover_no_wei=OutcomeWei(0),
        wrapped_erc20_address=wrapped_erc20_address,
    )


def migrate_via_fresh_mint(
    api_keys: APIKeys,
    inventory: PolymarketInventory,
    condition_id: HexBytes,
    user_address: ChecksumAddress,
    amount: OutcomeWei,
    outcome_index: int = 0,
    outcome_slot_count: int = 2,
    exchange_rate: ExchangeRate = "one_to_one",
    wrap_output: bool = False,
    web3: Web3 | None = None,
) -> MigrationResult:
    """Split a fresh stata full set inside the batch, then swap one outcome.

    The Safe must hold at least `amount_out` stata shares up front. After
    the batch the Safe holds: the user's source outcome ERC1155 and all
    non-migrated stata outcome ERC1155s (`amount_out` each).

    `wrap_output=True` adds two trailing legs: route the user's target
    outcome ERC1155 through `Wrapped1155Factory` to produce an ERC-20, then
    transfer that ERC-20 to the user.
    """
    safe_address = api_keys.safe_address_checksum
    if safe_address is None:
        raise ValueError("migrate_via_fresh_mint requires SAFE_ADDRESS.")

    ctf = PolymarketConditionalTokenContract()
    usdce = USDCeContract()
    stata = StataPolUSDCnContract()
    index_set = 1 << outcome_index

    source_position_id = ctf._position_id_for(
        usdce.address, condition_id, index_set, web3=web3
    )
    target_position_id = ctf._position_id_for(
        stata.address, condition_id, index_set, web3=web3
    )

    _precheck(
        ctf=ctf,
        safe_address=safe_address,
        condition_id=condition_id,
        user_address=user_address,
        source_position_id=source_position_id,
        amount_in=amount,
        web3=web3,
    )

    amount_out = _resolve_amount_out(amount, exchange_rate, stata, web3)
    safe_stata_balance = stata.balanceOf(for_address=safe_address, web3=web3)
    if safe_stata_balance.value < amount_out.value:
        raise ValueError(
            f"Safe holds {safe_stata_balance} stata; need {amount_out} to "
            "mint the full set. Fund the Safe with stata first."
        )

    w3 = web3 or ctf.get_web3()
    wrap_metadata: bytes | None = None
    wrapped_erc20_address: ChecksumAddress | None = None
    if wrap_output:
        name, symbol, decimals = _default_wrap_metadata(condition_id, outcome_index)
        wrap_metadata = Wrapped1155FactoryContract.encode_metadata(
            name, symbol, decimals
        )
        wrapped_erc20_address = Wrapped1155FactoryContract().get_wrapped_1155(
            multi_token=ctf.address,
            token_id=target_position_id,
            data=wrap_metadata,
            web3=w3,
        )

    calls = _build_fresh_mint_calls(
        web3=w3,
        ctf=ctf,
        target_collateral=stata,
        safe_address=safe_address,
        user_address=user_address,
        condition_id=condition_id,
        source_position_id=source_position_id,
        target_position_id=target_position_id,
        amount_in=amount,
        amount_out=amount_out,
        outcome_slot_count=outcome_slot_count,
        wrap_metadata=wrap_metadata,
    )
    logger.info(
        f"Migration path=fresh_mint condition={condition_id.to_0x_hex()} "
        f"user={user_address} amount_in={amount} amount_out={amount_out} "
        f"wrap_output={wrap_output}"
    )
    receipt = send_safe_batch_tx(
        web3=w3,
        safe_address=safe_address,
        from_private_key=api_keys.bet_from_private_key,
        calls=calls,
    )
    _register_inventory_keys(inventory, condition_id, outcome_slot_count, usdce, stata)
    return MigrationResult(
        receipt=receipt,
        source="fresh_mint",
        amount_in_wei=amount,
        amount_out_wei=amount_out,
        leftover_no_wei=amount_out,
        wrapped_erc20_address=wrapped_erc20_address,
    )


def migrate_position(
    api_keys: APIKeys,
    inventory: PolymarketInventory,
    condition_id: HexBytes,
    user_address: ChecksumAddress,
    amount: OutcomeWei,
    outcome_index: int = 0,
    outcome_slot_count: int = 2,
    exchange_rate: ExchangeRate = "one_to_one",
    auto_reconcile: bool = False,
    wrap_output: bool = False,
    web3: Web3 | None = None,
) -> MigrationResult:
    """Dispatch: take the inventory path when the Safe already has enough
    stata-<outcome>; otherwise mint a fresh full set inside the batch.

    `auto_reconcile=True` follows the migration with a separate tx that
    merges any matched YES+NO held by the Safe (per collateral) back into
    collateral. This is a no-op unless the Safe already held the counter
    outcome for either the USDC.e or stata leg.

    `wrap_output=True` routes the user's resulting outcome token through
    `Wrapped1155Factory`, so the user receives a tradeable ERC-20 instead
    of a raw CTF ERC-1155.
    """
    safe_address = api_keys.safe_address_checksum
    if safe_address is None:
        raise ValueError("migrate_position requires SAFE_ADDRESS.")

    ctf = PolymarketConditionalTokenContract()
    usdce = USDCeContract()
    stata = StataPolUSDCnContract()
    index_set = 1 << outcome_index
    target_position_id = ctf._position_id_for(
        stata.address, condition_id, index_set, web3=web3
    )
    amount_out = _resolve_amount_out(amount, exchange_rate, stata, web3)
    safe_target_balance = ctf.balanceOf(
        from_address=safe_address, position_id=target_position_id, web3=web3
    )

    if safe_target_balance.value >= amount_out.value:
        result = migrate_from_inventory(
            api_keys=api_keys,
            inventory=inventory,
            condition_id=condition_id,
            user_address=user_address,
            amount=amount,
            outcome_index=outcome_index,
            outcome_slot_count=outcome_slot_count,
            exchange_rate=exchange_rate,
            wrap_output=wrap_output,
            web3=web3,
        )
    else:
        result = migrate_via_fresh_mint(
            api_keys=api_keys,
            inventory=inventory,
            condition_id=condition_id,
            user_address=user_address,
            amount=amount,
            outcome_index=outcome_index,
            outcome_slot_count=outcome_slot_count,
            exchange_rate=exchange_rate,
            wrap_output=wrap_output,
            web3=web3,
        )

    if auto_reconcile:
        inventory.reconcile_full_sets(
            api_keys=api_keys,
            collateral_tokens={usdce.address: usdce, stata.address: stata},
            threshold=OutcomeWei(0),
            web3=web3,
        )

    return result
