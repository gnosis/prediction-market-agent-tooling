import typing as t

from eth_typing import ChecksumAddress, HexAddress
from pydantic import BaseModel, ConfigDict, Field

from prediction_market_agent_tooling.tools.hexbytes_custom import HexBytes


# Taken from https://github.com/gnosis/labs-contracts/blob/main/src/NFT/DoubleEndedStructQueue.sol
class MessageContainer(BaseModel):
    sender: ChecksumAddress
    recipient: ChecksumAddress
    message: bytes

    @staticmethod
    def from_tuple(values: tuple[t.Any, ...]) -> "MessageContainer":
        return MessageContainer(
            sender=values[0], recipient=values[1], message=values[2]
        )


class MessagePopped(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    agent_address: HexAddress = Field(alias="agentAddress")
    message: HexBytes
