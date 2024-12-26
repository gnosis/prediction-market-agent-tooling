import typing as t

from pydantic import BaseModel, ConfigDict, Field

from prediction_market_agent_tooling.gtypes import (
    HexBytes,
    Wei,
    ChecksumAddress,
    HexAddress,
)


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
