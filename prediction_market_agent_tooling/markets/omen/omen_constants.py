from web3 import Web3

from prediction_market_agent_tooling.gtypes import OutcomeStr

OMEN_TRUE_OUTCOME = OutcomeStr("Yes")
OMEN_FALSE_OUTCOME = OutcomeStr("No")

WRAPPED_XDAI_CONTRACT_ADDRESS = Web3.to_checksum_address(
    "0xe91d153e0b41518a2ce8dd3d7944fa863463a97d"
)
SDAI_CONTRACT_ADDRESS = Web3.to_checksum_address(
    "0xaf204776c7245bF4147c2612BF6e5972Ee483701"
)
METRI_SUPER_GROUP_CONTRACT_ADDRESS = Web3.to_checksum_address(
    "0x7147A7405fCFe5CFa30c6d5363f9f357a317d082"
)
