import typing as t
from typing import SupportsIndex

from hexbytes import HexBytes as HexBytesBase
from pydantic import GetJsonSchemaHandler
from pydantic.json_schema import JsonSchemaValue
from pydantic_core import CoreSchema
from pydantic_core.core_schema import (
    ValidationInfo,
    bytes_schema,
    plain_serializer_function_ser_schema,
    with_info_before_validator_function,
)

hex_serializer = plain_serializer_function_ser_schema(function=lambda x: x.hex())


class BaseHex:
    schema_pattern: t.ClassVar[str] = "^0x([0-9a-f][0-9a-f])*$"
    schema_examples: t.ClassVar[tuple[str, ...]] = (
        "0x",  # empty bytes
        "0xd4",
        "0xd4e5",
        "0xd4e56740",
        "0xd4e56740f876aef8",
        "0xd4e56740f876aef8c010b86a40d5f567",
        "0xd4e56740f876aef8c010b86a40d5f56745a118d0906a34e69aec8c0db1cb8fa3",  # web3-private-key-ok
    )

    @classmethod
    def __get_pydantic_json_schema__(
        cls, schema: CoreSchema, handler: GetJsonSchemaHandler
    ) -> JsonSchemaValue:
        json_schema = handler(schema)
        json_schema.update(
            format="binary",
            pattern=cls.schema_pattern,
            examples=list(cls.schema_examples),
        )
        return json_schema


class HexBytes(HexBytesBase, BaseHex):
    """
    Use when receiving ``hexbytes.HexBytes`` values. Includes
    a pydantic validator and serializer.
    """

    @classmethod
    def __get_pydantic_core_schema__(
        cls, source: type[t.Any], handler: t.Callable[[t.Any], CoreSchema]
    ) -> CoreSchema:
        schema = with_info_before_validator_function(
            cls.__eth_pydantic_validate__, bytes_schema()
        )
        schema["serialization"] = hex_serializer
        return schema

    @classmethod
    def fromhex(cls, hex_str: str) -> "HexBytes":
        value = hex_str[2:] if hex_str.startswith("0x") else hex_str
        return super().fromhex(value)

    def hex(
        self, sep: t.Union[str, bytes] | None = None, bytes_per_sep: "SupportsIndex" = 1
    ) -> str:
        result = super().hex()
        if isinstance(result, str) and result.startswith("0x"):
            return result
        return f"0x{result}"

    # def to_0x_hex(self) -> str:
    #     return self.hex() if self.hex().startswith("0x") else f"0x{self.hex()}"

    def __repr__(self) -> str:
        return f'HexBytes("{self.hex()}")'

    @classmethod
    def __eth_pydantic_validate__(
        cls, value: t.Any, info: ValidationInfo | None = None
    ) -> "HexBytes":
        return HexBytes(value)

    def as_int(self) -> int:
        return int(self.hex(), 16)
