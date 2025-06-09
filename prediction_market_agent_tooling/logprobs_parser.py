import math
from itertools import product
from typing import Any, Tuple, Type

from pydantic import BaseModel, ValidationError
from pydantic.fields import FieldInfo
from pydantic.type_adapter import TypeAdapter

from prediction_market_agent_tooling.loggers import logger


class LogprobDetail(BaseModel):
    token: str
    logprob: float
    prob: float


class FieldLogprobs(BaseModel):
    key: str
    logprobs: list[LogprobDetail]


class LogprobsParser:
    def __init__(
        self,
        skip_fields: list[str] | None = None,
        max_top_logprobs_length: int = 3,
        max_logprobs_length: int = 5,
    ):
        base_skip_fields = ["logprobs"]
        self.skip_fields = base_skip_fields + (skip_fields or [])
        self.max_top_logprobs_length = max_top_logprobs_length
        self.max_logprobs_length = max_logprobs_length

    def _get_logprobs_key_index(
        self, logprobs: list[dict[str, Any]], field_name: str
    ) -> int:
        key_candidate = ""
        for i, token in enumerate(logprobs):
            if token["token"] in field_name:
                key_candidate = key_candidate + token["token"]
            else:
                key_candidate = ""
            if key_candidate == field_name:
                return i

        return -1

    def _get_logprobs_indexes_for_result(
        self, logprobs: list[dict[str, Any]], key_index: int
    ) -> Tuple[int, int]:
        result_start_index = next(
            (
                i
                for i in range(key_index + 1, len(logprobs))
                if logprobs[i]["token"] in {":", ",", " ", ' "', '"', "\t", "\u00A0"}
            ),
            -1,
        )
        result_end_index = next(
            (
                i
                for i in range(result_start_index, len(logprobs))
                if logprobs[i]["token"]
                in {",", '"', ",\n", "\",\n'", '",\n', '"\n', "\n"}
            ),
            len(logprobs) - 1,
        )
        return result_start_index + 1, result_end_index

    def _is_correct_type(self, token: str, key_type: type | None) -> bool:
        if key_type is None:
            return True

        try:
            TypeAdapter(key_type).validate_python(token)
            return True
        except ValidationError:
            return False

    def _parse_valid_tokens_with__agg_probs(
        self,
        logprobs_list: list[tuple[dict[str, Any]]],
        field_info: FieldInfo,
        top_logprobs: int,
    ) -> list[dict[str, Any]]:
        results: list[dict[str, Any]] = [
            {
                "token": "".join(str(logprob["token"]) for logprob in logprobs),
                "logprob": sum(float(logprob["logprob"]) for logprob in logprobs),
                "prob": math.exp(
                    sum(float(logprob["logprob"]) for logprob in logprobs)
                ),
            }
            for logprobs in logprobs_list
        ]

        results_filtered: list[dict[str, Any]] = [
            result
            for result in results
            if self._is_correct_type(result["token"], field_info.annotation)
        ]

        sorted_results = sorted(
            results_filtered, key=lambda x: x["logprob"], reverse=True
        )
        return (
            sorted_results[:top_logprobs]
            if len(sorted_results) > top_logprobs
            else sorted_results
        )

    def parse_logprobs(
        self, logprobs: list[dict[str, Any]], target_model_cls: Type[BaseModel]
    ) -> list[FieldLogprobs]:
        results_for_keys = []

        for field_name, field_info in target_model_cls.model_fields.items():
            if field_name in self.skip_fields:
                continue

            key_index = self._get_logprobs_key_index(logprobs, field_name)

            if key_index < 0:
                logger.warning(f"Key {field_name} not found in logprobs")
                continue

            (
                result_start_index,
                result_end_index,
            ) = self._get_logprobs_indexes_for_result(logprobs, key_index)

            if result_start_index < 0 or result_end_index < 0:
                logger.warning(f"Error in parsing result for {field_name} in logprobs")
                continue

            valid_logprobs_raw = [
                logprobs[i]["top_logprobs"][: self.max_top_logprobs_length]
                for i in range(result_start_index, result_end_index)
                if logprobs[i]["top_logprobs"] is not None
            ]

            parsed_logprobs_data = self._parse_valid_tokens_with__agg_probs(
                list(product(*valid_logprobs_raw[: self.max_logprobs_length])),
                field_info,
                min(len(sublist) for sublist in valid_logprobs_raw),
            )

            results_for_keys.append(
                FieldLogprobs(
                    key=field_name,
                    logprobs=[LogprobDetail(**item) for item in parsed_logprobs_data],
                )
            )

        return results_for_keys
