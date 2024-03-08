from datetime import datetime
from decimal import Decimal
from typing import NewType, Union

from eth_typing.evm import (  # noqa: F401  # Import for the sake of easy importing with others from here.
    Address,
    ChecksumAddress,
    HexAddress,
    HexStr,
)
from hexbytes import (  # noqa: F401  # Import for the sake of easy importing with others from here.
    HexBytes,
)
from pydantic.types import SecretStr
from pydantic.v1.types import SecretStr as SecretStrV1
from web3.types import (  # noqa: F401  # Import for the sake of easy importing with others from here.
    TxParams,
    TxReceipt,
    Wei,
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
DatetimeWithTimezone = NewType("DatetimeWithTimezone", datetime)
ChainID = NewType("ChainID", int)


def usd_type(amount: Union[str, int, float, Decimal]) -> USD:
    return USD(Decimal(amount))


def wei_type(amount: Union[str, int]) -> Wei:
    return Wei(int(amount))


def xdai_type(amount: Union[str, int, float, Decimal]) -> xDai:
    return xDai(Decimal(amount))


def mana_type(amount: Union[str, int, float, Decimal]) -> Mana:
    return Mana(Decimal(amount))


def private_key_type(k: str) -> PrivateKey:
    return PrivateKey(SecretStr(k))


def secretstr_to_v1_secretstr(s: SecretStr) -> SecretStrV1:
    # Another library can be typed with v1, and then we need this ugly conversion.
    return SecretStrV1(s.get_secret_value())
