import typing as t

from eth_pydantic_types import HexStr
from eth_typing import ChecksumAddress, HexAddress
from pydantic import BaseModel, ConfigDict, Field
from web3 import Web3
from web3.types import Wei

from prediction_market_agent_tooling.tools.hexbytes_custom import HexBytes
from prediction_market_agent_tooling.tools.web3_utils import wei_to_xdai


# Taken from https://github.com/gnosis/labs-contracts/blob/main/src/NFT/DoubleEndedStructQueue.sol
class MessageContainer(BaseModel):
    sender: ChecksumAddress
    recipient: ChecksumAddress
    message: HexBytes
    value: Wei

    @staticmethod
    def from_tuple(values: tuple[t.Any, ...]) -> "MessageContainer":
        return MessageContainer(
            sender=values[0],
            recipient=values[1],
            message=HexBytes(values[2]),
            value=values[3],
        )


class LogMessageEvent(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    sender: HexAddress
    agent_address: HexAddress = Field(alias="agentAddress")
    message: HexBytes
    value: Wei

    def __str__(self) -> str:
        return f"""Sender: {self.sender}
    Value: {wei_to_xdai(self.value)} xDai
    Message: {Web3.to_text(hexstr=HexStr.from_bytes(self.message))}
    """
