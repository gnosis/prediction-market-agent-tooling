from web3 import Web3

from prediction_market_agent_tooling.config import APIKeys
from prediction_market_agent_tooling.gtypes import ChecksumAddress
from prediction_market_agent_tooling.tools.contract import (
    ConditionalTokenContract,
    ContractERC20BaseClass,
    ContractOnPolygonChain,
)


class USDCeContract(ContractERC20BaseClass, ContractOnPolygonChain):
    # USDC.e is used by Polymarket.
    address: ChecksumAddress = Web3.to_checksum_address(
        "0x2791Bca1f2de4661ED88A30C99A7a9449Aa84174"
    )


class PolymarketConditionalTokenContract(
    ConditionalTokenContract, ContractOnPolygonChain
):
    address: ChecksumAddress = Web3.to_checksum_address(
        "0x4D97DCd97eC945f40cF65F87097ACe5EA0476045"
    )

    def approve_if_not_approved(
        self, api_keys: APIKeys, for_address: ChecksumAddress, web3: Web3 | None = None
    ) -> None:
        is_approved = self.isApprovedForAll(
            owner=api_keys.public_key, for_address=for_address, web3=web3
        )
        if not is_approved:
            self.setApprovalForAll(
                api_keys=api_keys, for_address=for_address, approve=True, web3=web3
            )
