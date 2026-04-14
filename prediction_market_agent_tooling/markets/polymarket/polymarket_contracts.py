from web3 import Web3

from prediction_market_agent_tooling.config import APIKeys
from prediction_market_agent_tooling.gtypes import ChecksumAddress
from prediction_market_agent_tooling.markets.polymarket.constants import (
    STATA_POL_USDCN_ADDRESS,
)
from prediction_market_agent_tooling.tools.contract import (
    ConditionalTokenContract,
    ContractDepositableWrapperERC20OnPolygonChain,
    ContractERC20BaseClass,
    ContractERC4626OnPolygonChain,
    ContractOnPolygonChain,
)


class WPOLContract(ContractDepositableWrapperERC20OnPolygonChain):
    # Wrapped POL (formerly WMATIC) on Polygon.
    address: ChecksumAddress = Web3.to_checksum_address(
        "0x0d500B1d8E8eF31E21C99d1Db9A6444d3ADf1270"
    )


class USDCContract(ContractERC20BaseClass, ContractOnPolygonChain):
    # Native USDC on Polygon.
    address: ChecksumAddress = Web3.to_checksum_address(
        "0x3c499c542cEF5E3811e1192ce70d8cC03d5c3359"
    )


class USDCeContract(ContractERC20BaseClass, ContractOnPolygonChain):
    # USDC.e (bridged) is used by Polymarket.
    address: ChecksumAddress = Web3.to_checksum_address(
        "0x2791Bca1f2de4661ED88A30C99A7a9449Aa84174"
    )


class StataPolUSDCnContract(ContractERC4626OnPolygonChain):
    # Aave V3 static ERC-4626 wrapper over the aToken for USDC native on
    # Polygon. Asset is USDC native (0x3c499c54…). Non-rebasing.
    address: ChecksumAddress = STATA_POL_USDCN_ADDRESS


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
