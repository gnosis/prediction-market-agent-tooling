import re

import pytest
from pydantic.types import SecretStr

from prediction_market_agent_tooling.gtypes import IPFSCIDVersion0
from prediction_market_agent_tooling.tools.web3_utils import (
    NOT_REVERTED_ICASE_REGEX_PATTERN,
    byte32_to_ipfscidv0,
    ipfscidv0_to_byte32,
    private_key_to_public_key,
)


def test_private_key_to_public_key() -> None:
    ganache_private_key_example = (
        "0x94c589f92a38698b984605efbc0bff47208c43eac85ab6ea553cc9e17c4a49fe"
    )
    ganache_public_key_example = "0x4c24e51488429E013f259A7FB6Ac174c715BB66a"
    actual_public_key = private_key_to_public_key(
        SecretStr(ganache_private_key_example)
    )
    assert actual_public_key == ganache_public_key_example


def test_ipfs_hash_conversion() -> None:
    ipfs = IPFSCIDVersion0("QmRUkBx3FQHrMrt3bACh5XCSLwRjNcTpJreJp4p2qL3in3")

    as_bytes32 = ipfscidv0_to_byte32(ipfs)
    assert len(as_bytes32) == 32, "The length of the bytes32 should be 32"

    as_ipfs = byte32_to_ipfscidv0(as_bytes32)
    assert as_ipfs == ipfs, "The IPFS hash should be the same after conversion back"


@pytest.mark.parametrize(
    "string, matched",
    [
        ("blah blah", True),
        ("blah blah reverted", False),
        ("reverted blah blah", False),
        ("reveRted", False),
        ("", True),
    ],
)
def test_not_reverted_regex(string: str, matched: bool) -> None:
    p = re.compile(NOT_REVERTED_ICASE_REGEX_PATTERN)
    assert bool(p.match(string)) == matched
