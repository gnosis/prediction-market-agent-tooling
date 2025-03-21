import json

import pytest
from pydantic import BaseModel

from prediction_market_agent_tooling.gtypes import Token, Wei, xDai


class TestModel(BaseModel):
    t: Token
    w: Wei
    x: xDai


def test_generic_value_with_pydantic_1() -> None:
    m = TestModel(t=Token(1), w=Wei(2), x=xDai(3))
    assert m.t.value == 1
    assert m.w.value == 2
    assert m.x.value == 3


def test_generic_value_with_pydantic_2() -> None:
    m = TestModel(t=Token(1), w=Wei(2), x=xDai(3))

    dumped = m.model_dump()
    assert dumped == {
        "t": {"value": 1, "type": "Token"},
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
    m = {"t": Token(1), "w": Wei(2), "x": xDai(3)}
    assert (
        json.dumps(m)
        == """{"t": {"value": 1.0, "type": "Token"}, "w": {"value": 2, "type": "Wei"}, "x": {"value": 3.0, "type": "xDai"}}"""
    )


def test_incompatible_operations() -> None:
    t = Token(1)
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
    values = [Token(1), Token(2), Token(3)]
    assert type(sum(values)) == type(values[0])
    assert sum(values) == Token(6)

    assert sum([Token(0), Token(0)]) == 0, "Should work with zero."

    with pytest.raises(TypeError):
        assert sum(values) == 6, "Should not work when comparing with non zero"


def test_generic_value_str() -> None:
    assert str(Token(1)) == "1.0"
    assert str(Wei(1)) == "1"
    assert str(xDai(1)) == "1.0"


def test_generic_value_repr() -> None:
    assert repr(Token(1)) == "Token(1.0)"
    assert repr(Wei(1)) == "Wei(1)"
    assert repr(xDai(1)) == "xDai(1.0)"


def test_init_with_str() -> None:
    wei = Wei("1")
    assert isinstance(wei.value, int)
    assert wei.value == 1.0


def test_zero_equal() -> None:
    a = Token(0)
    assert a == 0
    assert not (a != 0)
