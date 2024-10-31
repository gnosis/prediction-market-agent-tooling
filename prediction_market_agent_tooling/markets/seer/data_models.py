import typing as t

from pydantic import BaseModel, ConfigDict, Field

from prediction_market_agent_tooling.tools.hexbytes_custom import HexBytes


class CreateCategoricalMarketsParams(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    publisher: str = Field(..., alias="publisherAddress")

    market_name: str = Field(..., alias="marketName")
    outcomes: list[str]
    # Only relevant for scalar markets
    question_start: t.Optional[str] = Field(..., alias="questionStart")
    question_end: t.Optional[str] = Field(..., alias="questionEnd")
    outcome_type: t.Optional[str] = Field(..., alias="outcomeType")

    parent_outcome: t.Optional[str] = Field(..., alias="parentOutcome")
    parent_market: t.Optional[HexBytes] = Field(..., alias="parentMarket")

    category: str
    lang: str

    lower_bound: t.Optional[int] = Field(..., alias="lowerBound")
    upper_bound: t.Optional[int] = Field(..., alias="upperBound")
    min_bond: int = Field(..., alias="minBond")
    opening_time: int = Field(..., alias="openingTime")
    token_names: list[str] = Field(..., alias="tokenNames")
