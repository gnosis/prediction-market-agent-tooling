import json

import pytest
from pydantic import BaseModel
from web3 import Web3

from prediction_market_agent_tooling.gtypes import (
    ChecksumAddress,
    CollateralToken,
    OutcomeWei,
    Wei,
    xDai,
)


class TestModel(BaseModel):
    t: CollateralToken
    w: Wei
    x: xDai


def test_generic_value_with_pydantic_1() -> None:
    m = TestModel(t=CollateralToken(1), w=Wei(2), x=xDai(3))
    assert m.t.value == 1
    assert m.w.value == 2
    assert m.x.value == 3


def test_generic_value_with_pydantic_2() -> None:
    m = TestModel(t=CollateralToken(1), w=Wei(2), x=xDai(3))

    dumped = m.model_dump()
    assert dumped == {
        "t": {"value": 1, "type": "CollateralToken"},
        "w": {"value": 2, "type": "Wei"},
        "x": {"value": 3, "type": "xDai"},
    }

    loaded = TestModel.model_validate(dumped)
    assert m == loaded


def test_generic_value_with_pydantic_3() -> None:
    dumped = {
        "t": "1",  # On purpose as str.
        "w": 2,
        "x": 3,
    }
    loaded = TestModel.model_validate(dumped)
    assert loaded.t.value == 1
    assert loaded.w.value == 2
    assert loaded.x.value == 3


def test_generic_value_with_json() -> None:
    m = {"t": CollateralToken(1), "w": Wei(2), "x": xDai(3)}
    assert (
        json.dumps(m)
        == """{"t": {"value": 1.0, "type": "CollateralToken"}, "w": {"value": 2, "type": "Wei"}, "x": {"value": 3.0, "type": "xDai"}}"""
    )


def test_incompatible_operations() -> None:
    t = CollateralToken(1)
    w = Wei(2)
    x = xDai(3)
    w_2 = w + Wei(5)
    w_3 = w + 0
    w_0 = Wei(0)

    with pytest.raises(TypeError):
        t + w  # type: ignore # Keep this here, if at any time mypy starts to complain that this is not an error, something went wrong.

    with pytest.raises(TypeError):
        w + x  # type: ignore # Keep this here, if at any time mypy starts to complain that this is not an error, something went wrong.

    assert w + w_2 == Wei(9)  # ok
    assert w + w_3 == Wei(4)  # ok
    assert w_0 == 0.0  # ok


def test_generic_value_sum() -> None:
    values = [CollateralToken(1), CollateralToken(2), CollateralToken(3)]
    assert type(sum(values)) == type(values[0])
    assert sum(values) == CollateralToken(6)

    assert sum([CollateralToken(0), CollateralToken(0)]) == 0, "Should work with zero."

    with pytest.raises(TypeError):
        assert sum(values) == 6, "Should not work when comparing with non zero"


def test_generic_value_str() -> None:
    assert str(CollateralToken(1)) == "1.0"
    assert str(Wei(1)) == "1"
    assert str(xDai(1)) == "1.0"


def test_generic_value_repr() -> None:
    assert repr(CollateralToken(1)) == "CollateralToken(1.0)"
    assert repr(Wei(1)) == "Wei(1)"
    assert repr(xDai(1)) == "xDai(1.0)"


def test_init_with_str() -> None:
    wei = Wei("1")
    assert isinstance(wei.value, int)
    assert wei.value == 1.0


def test_zero_equal() -> None:
    a = CollateralToken(0)
    assert a == 0
    assert not (a != 0)


def test_negative_values() -> None:
    original_value = CollateralToken(-1)
    assert original_value.value == -1
    as_wei = original_value.as_wei
    assert as_wei.as_token == original_value


def test_hash() -> None:
    a = CollateralToken(1)
    b = CollateralToken(1)
    c = CollateralToken(2)

    assert hash(a) == hash(b)
    assert hash(a) != hash(c)


def test_set_dict() -> None:
    a = CollateralToken(1)
    b = CollateralToken(2)

    d = {a: 1, b: 2}
    assert d[a] == 1
    assert d[b] == 2

    s = {a, b, b}
    assert len(s) == 2
    assert a in s
    assert b in s


class TestParams(BaseModel):
    market: ChecksumAddress
    outcome_indices: list[int]
    amounts: list[OutcomeWei]


def test_passing_around_big_ints() -> None:
    amounts_to_redeem = [OutcomeWei(0), OutcomeWei(506972912318042040), OutcomeWei(0)]

    params = TestParams(
        market=Web3.to_checksum_address("0x8298648810788EF1b2F7e0CD71553E200aB811B3"),
        outcome_indices=list(range(len([0, 1, 0]))),
        amounts=amounts_to_redeem,
    )

    assert params.amounts == amounts_to_redeem


def test_from_hex() -> None:
    assert Wei("0x1").value == 1


def test_from_negative_hex() -> None:
    assert Wei("-0x1").value == -1
