import math
from typing import Any, Tuple, TypedDict
from prediction_market_agent_tooling.loggers import logger
from itertools import product

class LogprobKey(TypedDict):
    name: str
    key_type: type
    valid_values: set[Any] | None

class LogprobsParser:
    def _get_logprobs_key_index(self, logprobs: list[dict[str, Any]], key: LogprobKey) -> int:
        key_candidate = ""
        key_position_end = 0
        for i, token in enumerate(logprobs):
            if token["token"] in key['name']:
                key_candidate = key_candidate+token["token"]
            else :
                key_candidate = ""
            if key_candidate == key['name']:
                return i
        
        return -1


    def _get_logprobs_indexes_for_result(self, logprobs: list[dict[str, Any]], key_index: int) -> Tuple[int, int]:

        result_start_index = next(
            (
                i for i in range(key_index+1, len(logprobs))
                if logprobs[i]["token"] in {":", ",", " "," \"","\"", "\t", "\u00A0"} 
            ),
            -1
        ) 
        result_end_index = next(
            (
                i for i in range(result_start_index, len(logprobs))
                if logprobs[i]["token"] in {",", "\"", ",\n", "\",\n'", "\",\n"} 
            ),
            -1
        )
        return result_start_index + 1, result_end_index


    def _is_correct_type(self, token: str, key_type: type) -> bool:
        try:
            key_type(token)
            return True
        except ValueError:
            return False


    def _parse_valid_tokens_with__agg_probs(self, logprobs_list: list[tuple[dict[str, Any]]], key: LogprobKey) -> list[dict[str, Any]]:
        results: list[dict[str, Any]] = [
            {
                "token": "".join(str(logprob["token"]) for logprob in logprobs),
                "logprob": sum(float(logprob["logprob"]) for logprob in logprobs),
                "prob": math.exp(sum(float(logprob["logprob"]) for logprob in logprobs))
            }
            for logprobs in logprobs_list
        ]
        
        results_filtered: list[dict[str, Any]] = [
            result for result in results 
            if self._is_correct_type(result["token"], key['key_type']) and
            (key['valid_values'] is None or result["token"] in key['valid_values'])
        ]
        
        return sorted(
            results_filtered, 
            key=lambda x: x["logprob"], 
            reverse=True
        )[:len(logprobs_list[0])]


    def parse_logprobs(self, logprobs: list[dict[str, Any]], keys: list[LogprobKey]) -> list[dict[str, Any]]:
        results_for_keys = []
        
        for key in keys:
            key_index = self._get_logprobs_key_index(logprobs, key)
            if key_index < 0:
                logger.warning(f"Key {key['name']} not found in logprobs")
                continue

            result_start_index, result_end_index = self._get_logprobs_indexes_for_result(logprobs, key_index)
            if result_start_index < 0 or result_end_index < 0:
                logger.warning(f"Error in parsing result for {key['name']} in logprobs")
                continue

            valid_logprobs = [logprobs[i]['top_logprobs'] for i in range(result_start_index, result_end_index)]
            results_for_keys.append(
                {
                    "key": key['name'],
                    "logprobs": self._parse_valid_tokens_with__agg_probs(list(product(*valid_logprobs)), key)
                }
            )

        return results_for_keys
