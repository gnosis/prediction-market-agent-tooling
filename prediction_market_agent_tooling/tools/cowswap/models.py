from enum import Enum
from typing import Optional

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    model_validator,
)
from typing_extensions import Self


class OrderKind(str, Enum):
    BUY = "buy"
    SELL = "sell"


class CowServer(str, Enum):
    GNOSIS_PROD = "https://api.cow.fi/xdai"
    GNOSIS_STAGING = "https://barn.api.cow.fi/xdai"


class BaseQuote(BaseModel):
    sell_token: str = Field(alias="sellToken")
    buy_token: str = Field(alias="buyToken")
    receiver: str
    app_data: Optional[str] = Field(default=None, alias="appData")
    sell_token_balance: str = Field(default="erc20", alias="sellTokenBalance")
    buy_token_balance: str = Field(default="erc20", alias="buyTokenBalance")
    price_quality: str = Field(default="fast", alias="priceQuality")
    signing_scheme: str = Field(default="eip712", alias="signingScheme")
    partially_fillable: bool = Field(default=False, alias="partiallyFillable")
    kind: OrderKind = Field(default=OrderKind.BUY)


class QuoteOutput(BaseQuote):
    fee_amount: str = Field(alias="feeAmount")
    buy_amount: str = Field(alias="buyAmount")
    sell_amount: str = Field(alias="sellAmount")
    valid_to: int = Field(alias="validTo")

    @model_validator(mode="after")
    def check_either_buy_or_sell_amount_set(self) -> Self:
        if self.sell_amount is None and self.buy_amount is None:
            raise ValueError("neither buy nor sell amounts set")
        if self.kind == "sell" and self.sell_amount is None:
            raise ValueError("sellAmountBeforeFee not set")
        elif self.kind == "buy" and self.buy_amount is None:
            raise ValueError("buyAmountAfterFee not set")
        return self


class QuoteInput(BaseQuote):
    from_: Optional[str] = Field(default=None, alias="from")
    sell_amount_before_fee: Optional[str] = Field(
        default=None, alias="sellAmountBeforeFee"
    )
    buy_amount_after_fee: Optional[str] = Field(default=None, alias="buyAmountAfterFee")
    model_config = ConfigDict(populate_by_name=True)
    valid_for: int = Field(alias="validFor")

    @model_validator(mode="after")
    def check_either_buy_or_sell_amount_set(self) -> Self:
        if self.sell_amount_before_fee is None and self.buy_amount_after_fee is None:
            raise ValueError("neither buy nor sell amounts set")
        if self.kind == "sell" and self.sell_amount_before_fee is None:
            raise ValueError("sellAmountBeforeFee not set")
        elif self.kind == "buy" and self.buy_amount_after_fee is None:
            raise ValueError("buyAmountAfterFee not set")
        return self


class OrderStatus(str, Enum):
    OPEN = "open"
    SCHEDULED = "scheduled"
    ACTIVE = "active"
    SOLVED = "solved"
    EXECUTING = "executing"
    TRADED = "traded"
    CANCELLED = "cancelled"
