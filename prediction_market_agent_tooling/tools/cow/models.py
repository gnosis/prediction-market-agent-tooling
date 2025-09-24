from enum import Enum
from typing import Annotated, Optional

from pydantic import BaseModel, BeforeValidator, ConfigDict
from sqlmodel import Field, SQLModel
from web3 import Web3

from prediction_market_agent_tooling.gtypes import ChecksumAddress, HexBytes, Wei
from prediction_market_agent_tooling.tools.datetime_utc import DatetimeUTC
from prediction_market_agent_tooling.tools.utils import utcnow


class MinimalisticTrade(BaseModel):
    sellToken: Annotated[ChecksumAddress, BeforeValidator(Web3.to_checksum_address)]
    buyToken: Annotated[ChecksumAddress, BeforeValidator(Web3.to_checksum_address)]
    orderUid: HexBytes
    txHash: HexBytes


class EthFlowData(BaseModel):
    refundTxHash: Optional[HexBytes]
    userValidTo: int


class PlacementError(str, Enum):
    QuoteNotFound = "QuoteNotFound"
    ValidToTooFarInFuture = "ValidToTooFarInFuture"
    PreValidationError = "PreValidationError"


class OnchainOrderData(BaseModel):
    sender: Annotated[ChecksumAddress, BeforeValidator(Web3.to_checksum_address)]
    placementError: Optional[PlacementError]


class OrderKind(str, Enum):
    buy = "buy"
    sell = "sell"


class SellTokenBalance(str, Enum):
    external = "external"
    internal = "internal"
    erc20 = "erc20"


class BuyTokenBalance(str, Enum):
    internal = "internal"
    erc20 = "erc20"


class SigningScheme(str, Enum):
    eip712 = "eip712"
    ethsign = "ethsign"
    presign = "presign"
    eip1271 = "eip1271"


class OrderClass(str, Enum):
    limit = "limit"
    liquidity = "liquidity"
    market = "market"


class OrderStatus(str, Enum):
    presignaturePending = "presignaturePending"
    open = "open"
    fulfilled = "fulfilled"
    cancelled = "cancelled"
    expired = "expired"


class Order(BaseModel):
    model_config = ConfigDict(validate_by_name=True, validate_by_alias=True)

    uid: str
    quoteId: int | None = None
    validTo: int
    sellAmount: Wei
    sellToken: Annotated[ChecksumAddress, BeforeValidator(Web3.to_checksum_address)]
    buyAmount: Wei
    buyToken: Annotated[ChecksumAddress, BeforeValidator(Web3.to_checksum_address)]
    receiver: Annotated[
        ChecksumAddress | None,
        BeforeValidator(
            lambda x: Web3.to_checksum_address(x) if x is not None else None
        ),
    ]
    feeAmount: Wei
    creationDate: DatetimeUTC
    kind: OrderKind
    partiallyFillable: bool
    sellTokenBalance: SellTokenBalance | None
    buyTokenBalance: BuyTokenBalance | None
    signingScheme: SigningScheme
    signature: HexBytes
    from_: Annotated[
        ChecksumAddress | None,
        BeforeValidator(
            lambda x: Web3.to_checksum_address(x) if x is not None else None
        ),
    ] = Field(None, alias="from")
    appData: str
    fullAppData: str | None
    appDataHash: HexBytes | None = None
    class_: str = Field(None, alias="class")
    owner: Annotated[ChecksumAddress, BeforeValidator(Web3.to_checksum_address)]
    executedSellAmount: Wei
    executedSellAmountBeforeFees: Wei
    executedBuyAmount: Wei
    executedFeeAmount: Wei | None
    invalidated: bool
    status: str
    isLiquidityOrder: bool | None
    ethflowData: EthFlowData | None = None
    onchainUser: Annotated[
        ChecksumAddress | None,
        BeforeValidator(
            lambda x: Web3.to_checksum_address(x) if x is not None else None
        ),
    ] = None
    executedFee: Wei
    executedFeeToken: Annotated[
        ChecksumAddress | None,
        BeforeValidator(
            lambda x: Web3.to_checksum_address(x) if x is not None else None
        ),
    ]


class RateLimit(SQLModel, table=True):
    __tablename__ = "rate_limit"
    __table_args__ = {"extend_existing": True}
    id: str = Field(primary_key=True)
    last_called_at: DatetimeUTC = Field(default_factory=utcnow)
