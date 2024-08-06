import json
import pprint
import re  # noqa: F401
from enum import Enum
from enum import StrEnum
from typing import Optional
from typing import Union, Any, Self, Set, Dict, TYPE_CHECKING

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StrictStr,
    ValidationError,
    field_validator,
    model_validator,
)


class OrderCreationAppData(BaseModel):
    """
    This field comes in two forms for backward compatibility. The hash form will eventually  stop being accepted.
    """

    # data type: str
    anyof_schema_1_validator: Optional[StrictStr] = Field(
        default=None,
        description='**Short**:  If you do not care about `appData`, set this field to `"{}"` and make sure that the order you signed for this request had its `appData` field set to `0xb48d38f93eaa084033fc5970bf96e559c33c4cdc07d889ab00b4d63f9590739d`.  **Long**:  A string encoding a JSON object like `"{"hello":"world"}"`.  This field determines the smart contract order\'s `appData` field, which is assumed to be set to the `keccak256` hash of the UTF-8 encoded bytes of this string. You must ensure that the signature that is part of this request indeed signed a smart contract order with the `appData` field set appropriately. If this isn\'t the case, signature verification will fail. For easier debugging it is recommended to additionally set the `appDataHash` field.  The field must be the encoding of a valid JSON object. The JSON object can contain arbitrary application specific data (JSON key values). The optional key `backend` is special. It **MUST** conform to the schema documented in `ProtocolAppData`.  The intended use of the other keys of the object is follow the standardized format defined [here](https://github.com/cowprotocol/app-data). Example:  ```json {   "version": "0.7.0",   "appCode": "YOUR_APP_CODE",   "metadata": {} } ```  The total byte size of this field\'s UTF-8 encoded bytes is limited to 1000. ',
    )
    # data type: str
    anyof_schema_2_validator: Optional[StrictStr] = Field(
        default=None,
        description="32 bytes encoded as hex with `0x` prefix. It's expected to be the hash of the stringified JSON object representing the `appData`. ",
    )
    if TYPE_CHECKING:
        actual_instance: Optional[Union[str]] = None
    else:
        actual_instance: Any = None
    any_of_schemas: Set[str] = {"str"}

    model_config = {
        "validate_assignment": True,
        "protected_namespaces": (),
    }

    def __init__(self, *args, **kwargs) -> None:
        if args:
            if len(args) > 1:
                raise ValueError(
                    "If a position argument is used, only 1 is allowed to set `actual_instance`"
                )
            if kwargs:
                raise ValueError(
                    "If a position argument is used, keyword arguments cannot be used."
                )
            super().__init__(actual_instance=args[0])
        else:
            super().__init__(**kwargs)

    @field_validator("actual_instance")
    def actual_instance_must_validate_anyof(cls, v):
        instance = OrderCreationAppData.model_construct()
        error_messages = []
        # validate data type: str
        try:
            instance.anyof_schema_1_validator = v
            return v
        except (ValidationError, ValueError) as e:
            error_messages.append(str(e))
        # validate data type: str
        try:
            instance.anyof_schema_2_validator = v
            return v
        except (ValidationError, ValueError) as e:
            error_messages.append(str(e))
        if error_messages:
            # no match
            raise ValueError(
                "No match found when setting the actual_instance in OrderCreationAppData with anyOf schemas: str. Details: "
                + ", ".join(error_messages)
            )
        else:
            return v

    @classmethod
    def from_dict(cls, obj: Dict[str, Any]) -> Self:
        return cls.from_json(json.dumps(obj))

    @classmethod
    def from_json(cls, json_str: str) -> Self:
        """Returns the object represented by the json string"""
        instance = cls.model_construct()
        error_messages = []
        # deserialize data into str
        try:
            # validation
            instance.anyof_schema_1_validator = json.loads(json_str)
            # assign value to actual_instance
            instance.actual_instance = instance.anyof_schema_1_validator
            return instance
        except (ValidationError, ValueError) as e:
            error_messages.append(str(e))
        # deserialize data into str
        try:
            # validation
            instance.anyof_schema_2_validator = json.loads(json_str)
            # assign value to actual_instance
            instance.actual_instance = instance.anyof_schema_2_validator
            return instance
        except (ValidationError, ValueError) as e:
            error_messages.append(str(e))

        if error_messages:
            # no match
            raise ValueError(
                "No match found when deserializing the JSON string into OrderCreationAppData with anyOf schemas: str. Details: "
                + ", ".join(error_messages)
            )
        else:
            return instance

    def to_json(self) -> str:
        """Returns the JSON representation of the actual instance"""
        if self.actual_instance is None:
            return "null"

        if hasattr(self.actual_instance, "to_json") and callable(
            self.actual_instance.to_json
        ):
            return self.actual_instance.to_json()
        else:
            return json.dumps(self.actual_instance)

    def to_dict(self) -> Optional[Union[dict[str, Any], str]]:
        """Returns the dict representation of the actual instance"""
        if self.actual_instance is None:
            return None

        if hasattr(self.actual_instance, "to_dict") and callable(
            self.actual_instance.to_dict
        ):
            return self.actual_instance.to_dict()
        else:
            return self.actual_instance

    def to_str(self) -> str:
        """Returns the string representation of the actual instance"""
        return pprint.pformat(self.model_dump())


class BuyTokenDestination(str, Enum):
    """
    Where should the `buyToken` be transferred to?
    """

    """
    allowed enum values
    """
    ERC20 = "erc20"
    INTERNAL = "internal"


class SellTokenSource(str, Enum):
    """
    Where should the `sellToken` be drawn from?
    """

    """
    allowed enum values
    """
    ERC20 = "erc20"
    INTERNAL = "internal"
    EXTERNAL = "external"


class OrderKind(StrEnum):
    BUY = "buy"
    SELL = "sell"


class SigningScheme(str, Enum):
    """
    How was the order signed?
    """

    """
    allowed enum values
    """
    EIP712 = "eip712"
    ETHSIGN = "ethsign"
    PRESIGN = "presign"
    EIP1271 = "eip1271"


class OrderQuoteSideKindBuy(str, Enum):
    """
    OrderQuoteSideKindBuy
    """

    """
    allowed enum values
    """
    BUY = "buy"


class CowMetadata(BaseModel):
    orderClass: dict[str, Any] = Field(default={"orderClass": "market"})
    quote: dict[str, Any] = Field(default={"slippageBips": 50})


class AppData(BaseModel):
    app_code: str | None = Field(default="CoW Swap", alias="appCode")
    version: str = Field(default="1.1.0")
    metadata: CowMetadata


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
    buy_amount: Optional[str] = Field(default=None, alias="buyAmount")
    sell_amount: Optional[str] = Field(default=None, alias="sellAmount")
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

    @model_validator(mode="after")
    def check_either_buy_or_sell_amount_set(self) -> Self:
        if self.sell_amount_before_fee is None and self.buy_amount_after_fee is None:
            raise ValueError("neither buy nor sell amounts set")
        if self.kind == "sell" and self.sell_amount_before_fee is None:
            raise ValueError("sellAmountBeforeFee not set")
        elif self.kind == "buy" and self.buy_amount_after_fee is None:
            raise ValueError("buyAmountAfterFee not set")
        return self


class OrderStatus(StrEnum):
    OPEN = "open"
    SCHEDULED = "scheduled"
    ACTIVE = "active"
    SOLVED = "solved"
    EXECUTING = "executing"
    TRADED = "traded"
    CANCELLED = "cancelled"
