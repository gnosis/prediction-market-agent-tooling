import typing as t
from datetime import datetime
from decimal import Decimal
from typing import NewType, Union

from eth_typing.evm import (  # noqa: F401  # Import for the sake of easy importing with others from here.
    Address,
    ChecksumAddress,
    HexAddress,
    HexStr,
)
from pydantic.types import SecretStr
from pydantic.v1.types import SecretStr as SecretStrV1
from web3.types import (  # noqa: F401  # Import for the sake of easy importing with others from here.
    Nonce,
    TxParams,
    TxReceipt,
    Wei,
)

from prediction_market_agent_tooling.tools.hexbytes import (  # noqa: F401  # Import for the sake of easy importing with others from here.
    HexBytes,
)

Wad = Wei  # Wei tends to be referred to as `wad` variable in contracts.
USD = NewType(
    "USD", Decimal
)  # Decimals are more precise than floats, good for finances.
PrivateKey = NewType("PrivateKey", SecretStr)
xDai = NewType("xDai", Decimal)
GNO = NewType("GNO", Decimal)
ABI = NewType("ABI", str)
OmenOutcomeToken = NewType("OmenOutcomeToken", int)
Probability = NewType("Probability", float)
Mana = NewType("Mana", Decimal)  # Manifold's "currency"
USDC = NewType("USDC", Decimal)
DatetimeWithTimezone = NewType("DatetimeWithTimezone", datetime)
ChainID = NewType("ChainID", int)


def usd_type(amount: Union[str, int, float, Decimal]) -> USD:
    return USD(Decimal(amount))


def wei_type(amount: Union[str, int]) -> Wei:
    return Wei(int(amount))


def omen_outcome_type(amount: Union[str, int, Wei]) -> OmenOutcomeToken:
    return OmenOutcomeToken(wei_type(amount))


def xdai_type(amount: Union[str, int, float, Decimal]) -> xDai:
    return xDai(Decimal(amount))


def mana_type(amount: Union[str, int, float, Decimal]) -> Mana:
    return Mana(Decimal(amount))


def usdc_type(amount: Union[str, int, float, Decimal]) -> USDC:
    return USDC(Decimal(amount))


def private_key_type(k: str) -> PrivateKey:
    return PrivateKey(SecretStr(k))


@t.overload
def secretstr_to_v1_secretstr(s: SecretStr) -> SecretStrV1:
    ...


@t.overload
def secretstr_to_v1_secretstr(s: None) -> None:
    ...


def secretstr_to_v1_secretstr(s: SecretStr | None) -> SecretStrV1 | None:
    # Another library can be typed with v1, and then we need this ugly conversion.
    return SecretStrV1(s.get_secret_value()) if s is not None else None


def int_to_hexbytes(v: int) -> HexBytes:
    # Example: 1 -> HexBytes("0x0000000000000000000000000000000000000000000000000000000000000001").
    return HexBytes.fromhex(format(v, "064x"))
