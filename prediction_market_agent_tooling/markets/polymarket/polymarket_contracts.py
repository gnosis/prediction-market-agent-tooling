from web3 import Web3

from prediction_market_agent_tooling.gtypes import ChecksumAddress
from prediction_market_agent_tooling.tools.contract import (
    ConditionalTokenContract,
    ContractERC20BaseClass,
    ContractOnPolygonChain,
)


class USDCContract(ContractERC20BaseClass, ContractOnPolygonChain):
    address: ChecksumAddress = Web3.to_checksum_address(
        "0x3c499c542cef5e3811e1192ce70d8cc03d5c3359"
    )


class PolymarketConditionalTokenContract(
    ConditionalTokenContract, ContractOnPolygonChain
):
    address: ChecksumAddress = Web3.to_checksum_address(
        "0x4D97DCd97eC945f40cF65F87097ACe5EA0476045"
    )
