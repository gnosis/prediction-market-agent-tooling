"""End-to-end demo: user hands over USDC.e-<outcome>, gets wrapped ERC-20 back.

Orchestrates the two sides of the flow in one script:

    === USER SIDE ===
    1. User EOA already holds some USDC.e.
    2. User mints a Polymarket outcome full set with `amount` USDC.e
       (so they hold `amount` of USDC.e-YES + `amount` of USDC.e-NO).
    3. User calls `setApprovalForAll(safe, true)` once (idempotent — skipped
       if already approved from a prior run).

    === SYSTEM SIDE ===
    4. Operator Safe runs the Safe MultiSend migration with `--wrap-output`:
       pulls user's USDC.e-<outcome>, splits its stata inventory, wraps the
       stata-<outcome> via `Wrapped1155Factory`, transfers the wrapped
       ERC-20 to the user.

    === RESULT ===
    User walks out holding only the wrapped ERC-20 (yield-bearing,
    CoW-tradeable). The operator Safe keeps the user's USDC.e-<outcome> +
    the leftover stata-<other outcome>.

Prereqs: Safe deployed and funded with stata; user EOA holds enough USDC.e
for the `amount` (and POL for gas).

Usage:
    python scripts/polymarket_demo_full_pipeline.py \\
        --condition-id 0x... \\
        --amount 0.005 \\
        [--outcome YES] \\
        [--user-private-key 0x...]   # defaults to BET_FROM_PRIVATE_KEY
"""

import os

import typer
from dotenv import load_dotenv
from web3 import Web3

from prediction_market_agent_tooling.config import APIKeys, RPCConfig
from prediction_market_agent_tooling.gtypes import (
    HexBytes,
    OutcomeWei,
    Wei,
    private_key_type,
)
from prediction_market_agent_tooling.loggers import logger
from prediction_market_agent_tooling.markets.polymarket.inventory import (
    InventoryKey,
    PolymarketInventory,
)
from prediction_market_agent_tooling.markets.polymarket.migration import (
    migrate_position,
)
from prediction_market_agent_tooling.markets.polymarket.polymarket_contracts import (
    PolymarketConditionalTokenContract,
    StataPolUSDCnContract,
    USDCeContract,
    Wrapped1155Contract,
)


def demo_full_pipeline(
    condition_id: str = typer.Option(..., help="0x-prefixed Polymarket conditionId."),
    amount: float = typer.Option(..., help="Amount of USDC.e to migrate (e.g. 0.005)."),
    outcome: str = typer.Option("YES", help="YES or NO."),
    user_private_key: str | None = typer.Option(
        None,
        help="User EOA key. Defaults to BET_FROM_PRIVATE_KEY (same EOA plays both roles).",
    ),
) -> None:
    load_dotenv()
    operator_keys = APIKeys()
    if operator_keys.safe_address_checksum is None:
        raise typer.BadParameter("SAFE_ADDRESS must be set for the operator side.")
    safe_address = operator_keys.safe_address_checksum

    user_pk = user_private_key or os.environ.get("BET_FROM_PRIVATE_KEY")
    if not user_pk:
        raise typer.BadParameter(
            "Need a user key — pass --user-private-key or set BET_FROM_PRIVATE_KEY."
        )
    user_keys = APIKeys(
        BET_FROM_PRIVATE_KEY=private_key_type(user_pk),
        SAFE_ADDRESS=None,  # user acts as EOA, never via Safe
    )
    user_address = user_keys.bet_from_address

    web3 = RPCConfig().get_polygon_web3()
    ctf = PolymarketConditionalTokenContract()
    usdce = USDCeContract()
    stata = StataPolUSDCnContract()
    cond = HexBytes(condition_id)
    amount_wei = OutcomeWei(int(amount * 1e6))

    if outcome.upper() == "YES":
        outcome_index = 0
    elif outcome.upper() == "NO":
        outcome_index = 1
    else:
        raise typer.BadParameter("--outcome must be YES or NO.")

    logger.info(f"User={user_address}  Safe={safe_address}")

    # ============================================================
    # USER SIDE
    # ============================================================
    logger.info("=== USER SIDE: mint outcome full set with USDC.e ===")
    usdce_balance = usdce.balanceOf(user_address, web3=web3)
    if usdce_balance.value < amount_wei.value:
        raise typer.BadParameter(
            f"User holds {usdce_balance} USDC.e; need {amount_wei}. "
            "Fund the user EOA with USDC.e first."
        )
    ctf.mint_full_set(
        api_keys=user_keys,
        collateral_token=usdce,
        condition_id=cond,
        amount=Wei(amount_wei.value),
        outcome_slot_count=2,
        web3=web3,
    )
    logger.info(
        f"User minted full set: {amount_wei} USDC.e-YES + {amount_wei} USDC.e-NO."
    )

    logger.info("=== USER SIDE: approve Safe as ERC-1155 operator (idempotent) ===")
    if ctf.isApprovedForAll(owner=user_address, for_address=safe_address, web3=web3):
        logger.info("Already approved — skipping.")
    else:
        ctf.setApprovalForAll(
            api_keys=user_keys, for_address=safe_address, approve=True, web3=web3
        )
        logger.info("Approval tx submitted.")

    # ============================================================
    # SYSTEM SIDE
    # ============================================================
    logger.info("=== SYSTEM SIDE: Safe MultiSend migration with ERC-20 wrap ===")
    inventory = PolymarketInventory(
        keys=[
            InventoryKey(condition_id=cond, collateral_address=usdce.address),
            InventoryKey(condition_id=cond, collateral_address=stata.address),
        ]
    )
    result = migrate_position(
        api_keys=operator_keys,
        inventory=inventory,
        condition_id=cond,
        user_address=user_address,
        amount=amount_wei,
        outcome_index=outcome_index,
        outcome_slot_count=2,
        wrap_output=True,
        web3=web3,
    )
    logger.info(
        f"Migration done. path={result.source} "
        f"wrapped_erc20={result.wrapped_erc20_address} "
        f"tx={result.receipt['transactionHash'].hex()}"
    )

    # ============================================================
    # RESULT
    # ============================================================
    logger.info("=== RESULT ===")
    assert result.wrapped_erc20_address is not None
    wrapped = Wrapped1155Contract(
        address=Web3.to_checksum_address(result.wrapped_erc20_address)
    )
    wrapped_bal = wrapped.balanceOf(user_address, web3=web3)
    logger.info(
        f"User holds {wrapped_bal} of {wrapped.symbol(web3=web3)} "
        f"(name={wrapped.name(web3=web3)}, address={result.wrapped_erc20_address})."
    )
    logger.info(
        "This ERC-20 is 1:1 redeemable for stata-<outcome> via "
        "Wrapped1155Factory.unwrap; tradeable on CoW / Uniswap V3 / Balancer; "
        "earns Aave yield on the underlying stata until market resolves."
    )


if __name__ == "__main__":
    typer.run(demo_full_pipeline)
