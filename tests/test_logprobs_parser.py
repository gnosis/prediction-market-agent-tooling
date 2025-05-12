from prediction_market_agent_tooling.logprobs_parser import LogprobsParser, LogprobKey
import pytest
import math
from typing import Any, List, Dict, Tuple, TypedDict

class LogprobToken(TypedDict):
    token: str
    logprob: float
    top_logprobs: List[Dict[str, Any]]

@pytest.fixture
def sample_logprobs() -> List[Dict[str, Any]]:
    return [
        {"token": "p", "logprob": -0.1, "top_logprobs": [{"token": "p", "logprob": -0.1}]},
        {"token": "_", "logprob": -0.2, "top_logprobs": [{"token": "_", "logprob": -0.2}]},
        {"token": "y", "logprob": -0.3, "top_logprobs": [{"token": "y", "logprob": -0.3}]},
        {"token": "e", "logprob": -0.4, "top_logprobs": [{"token": "e", "logprob": -0.4}]},
        {"token": "s", "logprob": -0.5, "top_logprobs": [{"token": "s", "logprob": -0.5}]},
        {"token": ":", "logprob": -0.6, "top_logprobs": [{"token": ":", "logprob": -0.6}]},
        {"token": " ", "logprob": -0.7, "top_logprobs": [{"token": " ", "logprob": -0.7}]},
        {"token": "0", "logprob": -0.8, "top_logprobs": [{"token": "0", "logprob": -0.8}]},
        {"token": ".", "logprob": -0.9, "top_logprobs": [{"token": ".", "logprob": -0.9}]},
        {"token": "8", "logprob": -1.0, "top_logprobs": [{"token": "8", "logprob": -1.0}]},
        {"token": ",", "logprob": -1.1, "top_logprobs": [{"token": ",", "logprob": -1.1}]},
    ]

@pytest.fixture
def sample_keys() -> List[LogprobKey]:
    return [
        LogprobKey(
            name="p_yes",
            key_type=float,
            valid_values=None
        )
    ]


@pytest.fixture
def parser() -> LogprobsParser:
    return LogprobsParser()


def test_get_logprobs_key_index(parser: LogprobsParser, sample_logprobs: List[Dict[str, Any]], sample_keys: List[LogprobKey]) -> None:
    key_index = parser._get_logprobs_key_index(sample_logprobs, sample_keys[0])
    assert key_index == 0

def test_get_logprobs_key_index_not_found(parser: LogprobsParser, sample_logprobs: List[Dict[str, Any]]) -> None:
    key = LogprobKey(name="nonexistent", key_type=str, valid_values=None)
    key_index = parser._get_logprobs_key_index(sample_logprobs, key)
    assert key_index == -1

def test_get_logprobs_indexes_for_result(parser: LogprobsParser, sample_logprobs: List[Dict[str, Any]], sample_keys: List[LogprobKey]) -> None:
    key_index = parser._get_logprobs_key_index(sample_logprobs, sample_keys[0])
    start_index, end_index = parser._get_logprobs_indexes_for_result(sample_logprobs, key_index)
    assert start_index == 7  # After "p_yes: "
    assert end_index == 10  # Before ","

def test_is_correct_type(parser: LogprobsParser) -> None:
    assert parser._is_correct_type("0.8", float) is True
    assert parser._is_correct_type("not_a_number", float) is False
    assert parser._is_correct_type("123", int) is True
    assert parser._is_correct_type("abc", int) is False

def test_parse_valid_tokens_with_agg_probs(parser: LogprobsParser, sample_logprobs: List[Dict[str, Any]], sample_keys: List[LogprobKey]) -> None:
    key_index = parser._get_logprobs_key_index(sample_logprobs, sample_keys[0])
    start_index, end_index = parser._get_logprobs_indexes_for_result(sample_logprobs, key_index)
    valid_logprobs = [sample_logprobs[i]['top_logprobs'] for i in range(start_index, end_index)]
    
    results = parser._parse_valid_tokens_with__agg_probs([tuple(lp) for lp in valid_logprobs], sample_keys[0])
    
    assert len(results) > 0
    assert "token" in results[0]
    assert "logprob" in results[0]
    assert "prob" in results[0]
    assert isinstance(results[0]["token"], str)
    assert isinstance(results[0]["logprob"], float)
    assert isinstance(results[0]["prob"], float)

def test_parse_logprobs(parser: LogprobsParser, sample_logprobs: List[Dict[str, Any]], sample_keys: List[LogprobKey]) -> None:
    results = parser.parse_logprobs(sample_logprobs, sample_keys)
    
    assert len(results) == 1
    assert results[0]["key"] == "p_yes"
    assert "logprobs" in results[0]
    assert len(results[0]["logprobs"]) > 0

def test_parse_logprobs_with_valid_values(parser: LogprobsParser, sample_logprobs: List[Dict[str, Any]]) -> None:
    key = LogprobKey(
        name="p_yes",
        key_type=float,
        valid_values={"0.8"}  # Only allow 0.8 as valid value
    )
    results = parser.parse_logprobs(sample_logprobs, [key])
    
    assert len(results) == 1
    assert results[0]["key"] == "p_yes"
    assert len(results[0]["logprobs"]) > 0
    assert all(result["token"] == "0.8" for result in results[0]["logprobs"])

def test_parse_logprobs_with_invalid_key(parser: LogprobsParser, sample_logprobs: List[Dict[str, Any]]) -> None:
    key = LogprobKey(
        name="nonexistent",
        key_type=str,
        valid_values=None
    )
    results = parser.parse_logprobs(sample_logprobs, [key])
    assert len(results) == 0

def test_logprob_calculation(parser: LogprobsParser) -> None:
    # Test with simple logprobs that are easy to verify
    test_logprobs: List[Dict[str, Any]] = [
        {"token": "0", "logprob": -0.5, "top_logprobs": [{"token": "0", "logprob": -0.5}]},
        {"token": ".", "logprob": -0.3, "top_logprobs": [{"token": ".", "logprob": -0.3}]},
        {"token": "5", "logprob": -0.2, "top_logprobs": [{"token": "5", "logprob": -0.2}]},
    ]
    
    key = LogprobKey(name="test", key_type=float, valid_values=None)
    key_index = parser._get_logprobs_key_index(test_logprobs, key)
    start_index, end_index = parser._get_logprobs_indexes_for_result(test_logprobs, key_index)
    valid_logprobs = [test_logprobs[i]['top_logprobs'] for i in range(start_index, end_index)]
    
    results = parser._parse_valid_tokens_with__agg_probs([tuple(lp) for lp in valid_logprobs], key)
    
    # Calculate expected values
    expected_logprob = -0.5 + -0.3 + -0.2  # Sum of individual logprobs
    expected_prob = math.exp(expected_logprob)
    
    assert len(results) > 0
    assert abs(results[0]["logprob"] - expected_logprob) < 1e-10
    assert abs(results[0]["prob"] - expected_prob) < 1e-10

def test_multiple_token_combinations(parser: LogprobsParser) -> None:
    # Test with multiple possible token combinations
    test_logprobs: List[Dict[str, Any]] = [
        {"token": "0", "logprob": -0.5, "top_logprobs": [
            {"token": "0", "logprob": -0.5},
            {"token": "1", "logprob": -0.6}
        ]},
        {"token": ".", "logprob": -0.3, "top_logprobs": [
            {"token": ".", "logprob": -0.3},
            {"token": ",", "logprob": -0.4}
        ]},
        {"token": "5", "logprob": -0.2, "top_logprobs": [
            {"token": "5", "logprob": -0.2},
            {"token": "6", "logprob": -0.3}
        ]},
    ]
    
    key = LogprobKey(name="test", key_type=float, valid_values=None)
    key_index = parser._get_logprobs_key_index(test_logprobs, key)
    start_index, end_index = parser._get_logprobs_indexes_for_result(test_logprobs, key_index)
    valid_logprobs = [test_logprobs[i]['top_logprobs'] for i in range(start_index, end_index)]
    
    results = parser._parse_valid_tokens_with__agg_probs([tuple(lp) for lp in valid_logprobs], key)
    
    # Verify that results are sorted by logprob in descending order
    for i in range(len(results) - 1):
        assert results[i]["logprob"] >= results[i + 1]["logprob"]
    
    # Verify that probabilities are properly calculated for each combination
    for result in results:
        # Find the corresponding tokens in the original logprobs
        tokens = result["token"]
        expected_logprob = 0.0
        for i, token in enumerate(tokens):
            for top_lp in test_logprobs[i]["top_logprobs"]:
                if top_lp["token"] == token:
                    expected_logprob += top_lp["logprob"]
                    break
        
        assert abs(result["logprob"] - expected_logprob) < 1e-10
        assert abs(result["prob"] - math.exp(expected_logprob)) < 1e-10
