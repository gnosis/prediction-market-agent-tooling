"""Atomically migrate a user's USDC.e Polymarket position to stata.

Calls `migrate_position()` from a Safe MultiSend; prints inventory before
and after so the demo is auditable. Routes via inventory if the Safe
already holds enough stata-<outcome>, else mints a fresh full set inside
the same batch.

Prerequisites:
  1. Operator Safe deployed and funded with stata
     (see polymarket_safe_create.py + polymarket_safe_fund_stata.py).
  2. The user holds USDC.e outcome ERC1155s for `--condition-id`
     (i.e. they have an open Polymarket position on that market).
  3. The user has called `setApprovalForAll(safe_address, True)` once on
     the CTF — see polymarket_approve_safe_for_user.py.

Usage:
    python scripts/polymarket_migrate_position.py \\
        --condition-id 0x... \\
        --user 0x... \\
        --amount 100 \\
        [--outcome YES] \\
        [--auto-reconcile] \\
        [--exchange-rate one_to_one|erc4626_shares]
"""

import typer
from web3 import Web3

from prediction_market_agent_tooling.config import APIKeys, RPCConfig
from prediction_market_agent_tooling.gtypes import HexBytes, OutcomeWei
from prediction_market_agent_tooling.loggers import logger
from prediction_market_agent_tooling.markets.polymarket.inventory import (
    InventoryKey,
    PolymarketInventory,
)
from prediction_market_agent_tooling.markets.polymarket.migration import (
    ExchangeRate,
    migrate_position,
)
from prediction_market_agent_tooling.markets.polymarket.polymarket_contracts import (
    StataPolUSDCnContract,
    USDCeContract,
)


def _print_inventory(
    label: str,
    inventory: PolymarketInventory,
    owner: str,
    web3: Web3,
) -> None:
    snapshots = inventory.refresh_from_chain(
        owner=Web3.to_checksum_address(owner), web3=web3
    )
    logger.info(f"--- {label} (owner={owner}) ---")
    for snap in snapshots:
        balances = [b.value for b in snap.balances_wei]
        logger.info(
            f"  cond={snap.key.condition_id.to_0x_hex()[:10]}… "
            f"collateral={snap.key.collateral_address} balances={balances}"
        )


def migrate_polymarket_position(
    condition_id: str = typer.Option(..., help="0x-prefixed Polymarket conditionId."),
    user: str = typer.Option(..., help="User EOA address holding the USDC.e tokens."),
    amount: float = typer.Option(..., help="Amount of USDC.e-<outcome> to migrate."),
    outcome: str = typer.Option(
        "YES", help="Outcome to migrate: YES (index 0) or NO (index 1)."
    ),
    exchange_rate: ExchangeRate = typer.Option(
        "one_to_one", help="Pricing rule: one_to_one (demo) or erc4626_shares (strict)."
    ),
    auto_reconcile: bool = typer.Option(
        False,
        help="After migration, merge any matched YES+NO Safe holds back to collateral.",
    ),
    wrap_output: bool = typer.Option(
        False,
        help="Wrap the user's output outcome token into an ERC-20 via Wrapped1155Factory (CoW-tradeable).",
    ),
) -> None:
    api_keys = APIKeys()
    if api_keys.safe_address_checksum is None:
        raise typer.BadParameter(
            "SAFE_ADDRESS env var must be set to the operator Safe."
        )

    web3 = RPCConfig().get_polygon_web3()
    cond = HexBytes(condition_id)
    user_addr = Web3.to_checksum_address(user)
    amount_wei = OutcomeWei(int(amount * 1e6))

    if outcome.upper() == "YES":
        outcome_index = 0
    elif outcome.upper() == "NO":
        outcome_index = 1
    else:
        raise typer.BadParameter("--outcome must be YES or NO.")

    inventory = PolymarketInventory(
        keys=[
            InventoryKey(condition_id=cond, collateral_address=USDCeContract().address),
            InventoryKey(
                condition_id=cond,
                collateral_address=StataPolUSDCnContract().address,
            ),
        ]
    )

    _print_inventory(
        "Safe BEFORE", inventory, str(api_keys.safe_address_checksum), web3
    )
    _print_inventory("User BEFORE", inventory, user, web3)

    result = migrate_position(
        api_keys=api_keys,
        inventory=inventory,
        condition_id=cond,
        user_address=user_addr,
        amount=amount_wei,
        outcome_index=outcome_index,
        outcome_slot_count=2,
        exchange_rate=exchange_rate,
        auto_reconcile=auto_reconcile,
        wrap_output=wrap_output,
        web3=web3,
    )

    logger.info(
        f"Migration done. path={result.source} "
        f"in={result.amount_in_wei} out={result.amount_out_wei} "
        f"leftover_no={result.leftover_no_wei} "
        f"wrapped_erc20={result.wrapped_erc20_address} "
        f"tx={result.receipt['transactionHash'].hex()}"
    )

    _print_inventory("Safe AFTER", inventory, str(api_keys.safe_address_checksum), web3)
    _print_inventory("User AFTER", inventory, user, web3)


if __name__ == "__main__":
    typer.run(migrate_polymarket_position)
