import math
from typing import Any, Dict, List, Literal

import pytest
from pydantic import BaseModel

from prediction_market_agent_tooling.logprobs_parser import LogprobsParser


class DummyModel(BaseModel):
    p_yes: float


class DummyModelWithInvalidValues(BaseModel):
    p_no: float


class DummyModelWithValidatedValues(BaseModel):
    p_yes: Literal["0.8"]


@pytest.fixture
def sample_logprobs() -> List[Dict[str, Any]]:
    return [
        {
            "token": "p",
            "logprob": -0.1,
            "top_logprobs": [{"token": "p", "logprob": -0.1}],
        },
        {
            "token": "_",
            "logprob": -0.2,
            "top_logprobs": [{"token": "_", "logprob": -0.2}],
        },
        {
            "token": "y",
            "logprob": -0.3,
            "top_logprobs": [{"token": "y", "logprob": -0.3}],
        },
        {
            "token": "e",
            "logprob": -0.4,
            "top_logprobs": [{"token": "e", "logprob": -0.4}],
        },
        {
            "token": "s",
            "logprob": -0.5,
            "top_logprobs": [{"token": "s", "logprob": -0.5}],
        },
        {
            "token": ":",
            "logprob": -0.6,
            "top_logprobs": [{"token": ":", "logprob": -0.6}],
        },
        {
            "token": "0",
            "logprob": -0.8,
            "top_logprobs": [{"token": "0", "logprob": -0.8}],
        },
        {
            "token": ".",
            "logprob": -0.9,
            "top_logprobs": [{"token": ".", "logprob": -0.9}],
        },
        {
            "token": "8",
            "logprob": -1.0,
            "top_logprobs": [{"token": "8", "logprob": -1.0}],
        },
        {
            "token": ",",
            "logprob": -1.1,
            "top_logprobs": [{"token": ",", "logprob": -1.1}],
        },
    ]


@pytest.fixture
def parser() -> LogprobsParser:
    return LogprobsParser()


def test_get_logprobs_key_index(
    parser: LogprobsParser,
    sample_logprobs: List[Dict[str, Any]],
) -> None:
    key_index = parser._get_logprobs_key_index(sample_logprobs, "p_yes")
    assert key_index == 4


def test_get_logprobs_key_index_not_found(
    parser: LogprobsParser, sample_logprobs: List[Dict[str, Any]]
) -> None:
    key_index = parser._get_logprobs_key_index(sample_logprobs, "nonexistent")
    assert key_index == -1


def test_get_logprobs_indexes_for_result(
    parser: LogprobsParser,
    sample_logprobs: List[Dict[str, Any]],
) -> None:
    key_index = parser._get_logprobs_key_index(sample_logprobs, "p_yes")
    start_index, end_index = parser._get_logprobs_indexes_for_result(
        sample_logprobs, key_index
    )
    assert start_index == 6  # After "p_yes: "
    assert end_index == 9  # Before ","


def test_is_correct_type(parser: LogprobsParser) -> None:
    assert parser._is_correct_type("0.8", float) is True
    assert parser._is_correct_type("not_a_number", float) is False
    assert parser._is_correct_type("123", int) is True
    assert parser._is_correct_type("abc", int) is False


def test_parse_valid_tokens_with_agg_probs(
    parser: LogprobsParser,
    sample_logprobs: List[Dict[str, Any]],
) -> None:
    dummy_yes_info = DummyModel.model_fields["p_yes"]
    key_index = parser._get_logprobs_key_index(sample_logprobs, "p_yes")
    start_index, end_index = parser._get_logprobs_indexes_for_result(
        sample_logprobs, key_index
    )
    valid_logprobs = [
        sample_logprobs[i]["top_logprobs"] for i in range(start_index, end_index)
    ]

    results = parser._parse_valid_tokens_with__agg_probs(
        [tuple(lp) for lp in valid_logprobs], dummy_yes_info
    )

    assert len(results) > 0
    assert "token" in results[0]
    assert "logprob" in results[0]
    assert "prob" in results[0]
    assert isinstance(results[0]["token"], str)
    assert isinstance(results[0]["logprob"], float)
    assert isinstance(results[0]["prob"], float)


def test_parse_logprobs(
    parser: LogprobsParser,
    sample_logprobs: List[Dict[str, Any]],
) -> None:
    results = parser.parse_logprobs(sample_logprobs, DummyModel)

    assert len(results) == 1
    assert results[0].key == "p_yes"
    assert results[0].logprobs is not None
    assert len(results[0].logprobs) > 0


def test_parse_logprobs_with_valid_values(
    parser: LogprobsParser, sample_logprobs: List[Dict[str, Any]]
) -> None:
    results = parser.parse_logprobs(sample_logprobs, DummyModelWithValidatedValues)

    assert len(results) == 1
    assert results[0].key == "p_yes"
    assert len(results[0].logprobs) > 0
    assert all(result.token == "0.8" for result in results[0].logprobs)


def test_parse_logprobs_with_invalid_key(
    parser: LogprobsParser, sample_logprobs: List[Dict[str, Any]]
) -> None:
    results = parser.parse_logprobs(sample_logprobs, DummyModelWithInvalidValues)
    assert len(results) == 0


def test_logprob_calculation(parser: LogprobsParser) -> None:
    # Test with simple logprobs that are easy to verify
    valid_logprobs: list[tuple[dict[str, Any]]] = [
        (
            {"token": "0", "logprob": -0.5},
            {"token": ".", "logprob": -0.3},
            {"token": "5", "logprob": -0.2},
        )  # type: ignore
    ]

    dummy_yes_info = DummyModel.model_fields["p_yes"]
    results = parser._parse_valid_tokens_with__agg_probs(valid_logprobs, dummy_yes_info)

    # Calculate expected values
    expected_logprob = -0.5 + -0.3 + -0.2  # Sum of individual logprobs
    expected_prob = math.exp(expected_logprob)

    assert len(results) > 0
    assert results[0]["logprob"] == expected_logprob
    assert results[0]["prob"] == expected_prob


def test_get_logprobs_key_index_partial_match(
    parser: LogprobsParser, sample_logprobs: List[Dict[str, Any]]
) -> None:
    key_index = parser._get_logprobs_key_index(sample_logprobs, "p_y")

    assert key_index != 4
