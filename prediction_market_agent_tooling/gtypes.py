import typing as t
from decimal import Decimal
from typing import NewType

from eth_typing.evm import (  # noqa: F401  # Import for the sake of easy importing with others from here.
    Address,
    ChecksumAddress,
    HexAddress,
    HexStr,
)
from pydantic.types import SecretStr
from pydantic.v1.types import SecretStr as SecretStrV1
from web3 import Web3
from web3.types import (  # noqa: F401  # Import for the sake of easy importing with others from here.
    Nonce,
    TxParams,
    TxReceipt,
)
from web3.types import Wei as Web3Wei

from prediction_market_agent_tooling.tools._generic_value import _GenericValue
from prediction_market_agent_tooling.tools.datetime_utc import (  # noqa: F401  # Import for the sake of easy importing with others from here.
    DatetimeUTC,
)
from prediction_market_agent_tooling.tools.hexbytes_custom import (  # noqa: F401  # Import for the sake of easy importing with others from here.
    HexBytes,
)


class Token(_GenericValue[int | float | str | Decimal], parser=float):
    """
    Represents any token in its decimal form, it could be 1.1 GNO, WXDAI, XDAI, Mana, whatever. We don't know the currency, just that it's in the decimal form.
    """

    @property
    def as_wei(self) -> "Wei":
        return Wei(Web3.to_wei(self.value, "ether"))


class OutcomeToken(_GenericValue[int | float | str | Decimal], parser=float):
    """
    Represents outcome tokens in market in decimal form.
    After you redeem the outcome tokens, 1 OutcomeToken equals to 1 Token, but before, it's important to distinguish between them.
    For example, it's a big difference if you are going to sell 1 OutcomeToken, or 1 (collateral) Token.
    But still, Token and OutcomeToken needs to be handled together in many cases, use available properties to convert between them explicitly.
    """

    @staticmethod
    def from_token(token: Token) -> "OutcomeToken":
        return OutcomeToken(token.value)

    @property
    def as_outcome_wei(self) -> "OutcomeWei":
        return OutcomeWei(Web3.to_wei(self.value, "ether"))

    @property
    def as_token(self) -> Token:
        """
        OutcomeToken is essentialy Token as well, when you know you really need to convert it, you can convert it explicitly using this.
        """
        return Token(self.value)


class USD(_GenericValue[int | float | str | Decimal], parser=float):
    """Represents values in USD."""


class xDai(_GenericValue[int | float | str | Decimal], parser=float):
    """Represents values in xDai."""

    @property
    def as_token(self) -> Token:
        """
        xDai is essentialy Token as well, when you know you need to pass it, you can convert it using this.
        """
        return Token(self.value)

    @property
    def as_xdai_wei(self) -> "xDaiWei":
        return xDaiWei(Web3.to_wei(self.value, "ether"))


class Mana(_GenericValue[int | float | str | Decimal], parser=float):
    """Represents values in Manifold's Mana."""


class USDC(_GenericValue[int | float | str | Decimal], parser=float):
    """Represents values in USDC."""


class Wei(_GenericValue[Web3Wei | int | str, Web3Wei], parser=Web3Wei):
    """Represents values in Wei. We don't know what currency, but in its integer form called Wei."""

    @property
    def as_token(self) -> Token:
        return Token(Web3.from_wei(self.value, "ether"))


class OutcomeWei(_GenericValue[Web3Wei | int | str, Web3Wei], parser=Web3Wei):
    """
    Similar to OutcomeToken, but in Wei units.
    """

    @staticmethod
    def from_wei(wei: Wei) -> "OutcomeWei":
        return OutcomeWei(wei.value)

    @property
    def as_outcome_token(self) -> OutcomeToken:
        return OutcomeToken(Web3.from_wei(self.value, "ether"))

    @property
    def as_wei(self) -> Wei:
        """
        OutcomeWei is essentialy Wei as well, when you know you need to pass it, you can convert it using this.
        """
        return Wei(self.value)


class xDaiWei(_GenericValue[Web3Wei | int | str, Web3Wei], parser=Web3Wei):
    """Represents xDai in Wei, like 1.9 xDai is 1.9 * 10**18 Wei. In contrast to just `Wei`, we don't know what unit Wei is (Wei of GNO, sDai, or whatever), but xDaiWei is xDai converted to Wei."""

    @property
    def as_xdai(self) -> xDai:
        return xDai(Web3.from_wei(self.value, "ether"))

    @property
    def as_wei(self) -> Wei:
        """
        xDaiWei is essentialy Wei as well, when you know you need to pass it, you can convert it using this.
        """
        return Wei(self.value)


PrivateKey = NewType("PrivateKey", SecretStr)
ABI = NewType("ABI", str)
OutcomeStr = NewType("OutcomeStr", str)
Probability = NewType("Probability", float)
ChainID = NewType("ChainID", int)
IPFSCIDVersion0 = NewType("IPFSCIDVersion0", str)


def private_key_type(k: str) -> PrivateKey:
    return PrivateKey(SecretStr(k))


@t.overload
def secretstr_to_v1_secretstr(s: SecretStr) -> SecretStrV1: ...


@t.overload
def secretstr_to_v1_secretstr(s: None) -> None: ...


def secretstr_to_v1_secretstr(s: SecretStr | None) -> SecretStrV1 | None:
    # Another library can be typed with v1, and then we need this ugly conversion.
    return SecretStrV1(s.get_secret_value()) if s is not None else None


def int_to_hexbytes(v: int) -> HexBytes:
    # Example: 1 -> HexBytes("0x0000000000000000000000000000000000000000000000000000000000000001"). # web3-private-key-ok
    return HexBytes.fromhex(format(v, "064x"))
