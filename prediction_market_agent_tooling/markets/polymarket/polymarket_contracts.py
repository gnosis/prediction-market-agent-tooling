from web3 import Web3

from prediction_market_agent_tooling.gtypes import ChecksumAddress
from prediction_market_agent_tooling.tools.contract import (
    ContractERC20BaseClass,
    ContractOnPolygonChain,
)


class USDCContract(ContractERC20BaseClass, ContractOnPolygonChain):
    address: ChecksumAddress = Web3.to_checksum_address(
        "0x3c499c542cef5e3811e1192ce70d8cc03d5c3359"
    )
