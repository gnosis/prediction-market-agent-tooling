import typing as t

from pydantic import BaseModel, Field, ConfigDict

from prediction_market_agent_tooling.gtypes import (
    HexBytes,
    Wei,
    ChecksumAddress,
)


# Taken from https://github.com/gnosis/labs-contracts/blob/main/src/NFT/DoubleEndedStructQueue.sol
class MessageContainer(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    sender: ChecksumAddress
    recipient: ChecksumAddress = Field(alias="agentAddress")
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
