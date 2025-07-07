import os

from web3 import Web3

from prediction_market_agent_tooling.chains import POLYGON_CHAIN_ID
from prediction_market_agent_tooling.gtypes import ABI, ChecksumAddress, HexBytes
from prediction_market_agent_tooling.loggers import logger
from prediction_market_agent_tooling.markets.omen.omen_contracts import (
    OmenConditionalTokenContract,
)
from prediction_market_agent_tooling.tools.contract import abi_field_validator


class PolymarketConditionalTokenContract(OmenConditionalTokenContract):
    # Contract ABI taken from https://gnosisscan.io/address/0xCeAfDD6bc0bEF976fdCd1112955828E00543c0Ce#code.
    abi: ABI = abi_field_validator(
        os.path.join(
            os.path.dirname(os.path.realpath(__file__)),
            "../../abis/omen_fpmm_conditionaltokens.abi.json",
        )
    )
    address: ChecksumAddress = Web3.to_checksum_address(
        "0x4D97DCd97eC945f40cF65F87097ACe5EA0476045"
    )
    CHAIN_ID = POLYGON_CHAIN_ID

    def get_resolved_outcome_idx(
        self, condition_id: HexBytes, web3: Web3 | None = None
    ) -> int | None:
        # This handles only binary outcomes for now, and raises Exception otherwise.

        if not self.is_condition_resolved(condition_id=condition_id, web3=web3):
            logger.debug("Condition not yet resolved, returning resolved index None.")
            return None

        outcome_slot_count = self.getOutcomeSlotCount(condition_id, web3=web3)
        # Check if outcome resolved, else return None.

        payout_numerators = [
            self.payoutNumerators(condition_id, i, web3=web3)
            for i in range(outcome_slot_count)
        ]

        # Check that exactly one outcome has a non-zero payout
        non_zero_outcomes = [i for i, num in enumerate(payout_numerators) if num > 0]
        if len(non_zero_outcomes) != 1:
            raise ValueError(
                f"Only binary markets are supported.Expected exactly one non-zero payout numerator, "
                f"but found {len(non_zero_outcomes)}: {payout_numerators}"
            )

        return non_zero_outcomes[0]
