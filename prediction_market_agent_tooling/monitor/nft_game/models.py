from pydantic import BaseModel, Field

from prediction_market_agent_tooling.tools.hexbytes_custom import HexBytes


class ERC721Transfer(BaseModel):
    block_number: int = Field(alias="blockNumber")
    transaction_hash: HexBytes = Field(alias="transactionHash")
    address: HexBytes
    event: str
    from_address: HexBytes
    to_address: HexBytes
    token_id: int

    @classmethod
    def from_event_log(cls, log: dict) -> "ERC721Transfer":
        d = {
            "from_address": log["args"]["from"],
            "to_address": log["args"]["to"],
            "token_id": log["args"]["tokenId"],
        }
        return ERC721Transfer.model_validate({**d, **log})
