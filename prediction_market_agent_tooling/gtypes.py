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
from web3.types import Wei

Wad = Wei  # Wei tends to be referred to as `wad` variable in contracts.
USD = NewType(
    "USD", Decimal
)  # Decimals are more precise than floats, good for finances.
PrivateKey = NewType("PrivateKey", str)
xDai = NewType("xDai", Decimal)
GNO = NewType("GNO", Decimal)
ABI = NewType("ABI", str)
OmenOutcomeToken = NewType("OmenOutcomeToken", int)
Probability = NewType("Probability", float)
Mana = NewType("Mana", Decimal)  # Manifold's "currency"


def usd_type(amount: Union[str, int, float, Decimal]) -> USD:
    return USD(Decimal(amount))


def wei_type(amount: Union[str, int]) -> Wei:
    return Wei(int(amount))


def xdai_type(amount: Union[str, int, float, Decimal]) -> xDai:
    return xDai(Decimal(amount))


def mana_type(amount: Union[str, int, float, Decimal]) -> Mana:
    return Mana(Decimal(amount))
