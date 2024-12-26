from pydantic import BaseModel, ConfigDict, Field

from prediction_market_agent_tooling.gtypes import HexBytes


class SeerParentMarket(BaseModel):
    id: HexBytes


class SeerMarket(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    id: HexBytes
    title: str = Field(alias="marketName")
    outcomes: list[str]
    parent_market: SeerParentMarket | None = Field(alias="parentMarket")
    wrapped_tokens: list[HexBytes] = Field(alias="wrappedTokens")


class SeerToken(BaseModel):
    id: HexBytes
    name: str
    symbol: str


class SeerPool(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    id: HexBytes
    liquidity: int
    token0: SeerToken
    token1: SeerToken
