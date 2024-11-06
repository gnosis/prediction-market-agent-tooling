import typing as t

import tenacity
from pydantic import BaseModel
from subgrounds import FieldPath, Subgrounds

from prediction_market_agent_tooling.config import APIKeys
from prediction_market_agent_tooling.loggers import logger
from prediction_market_agent_tooling.tools.singleton import SingletonMeta

T = t.TypeVar("T", bound=BaseModel)


class BaseSubgraphHandler(metaclass=SingletonMeta):
    def __init__(self) -> None:
        self.sg = Subgrounds()
        # Patch methods to retry on failure.
        self.sg.query_json = tenacity.retry(
            stop=tenacity.stop_after_attempt(3),
            wait=tenacity.wait_fixed(1),
            after=lambda x: logger.debug(f"query_json failed, {x.attempt_number=}."),
        )(self.sg.query_json)
        self.sg.load_subgraph = tenacity.retry(
            stop=tenacity.stop_after_attempt(3),
            wait=tenacity.wait_fixed(1),
            after=lambda x: logger.debug(f"load_subgraph failed, {x.attempt_number=}."),
        )(self.sg.load_subgraph)

        self.keys = APIKeys()

    def _parse_items_from_json(
        self, result: list[dict[str, t.Any]]
    ) -> list[dict[str, t.Any]]:
        """subgrounds return a weird key as a dict key"""
        items = []
        for result_chunk in result:
            for k, v in result_chunk.items():
                # subgrounds might pack all items as a list, indexed by a key, or pack it as a dictionary (if one single element)
                if v is None:
                    continue
                elif isinstance(v, dict):
                    items.extend([v])
                else:
                    items.extend(v)
        return items

    def do_query(self, fields: list[FieldPath], pydantic_model: t.Type[T]) -> list[T]:
        result = self.sg.query_json(fields)
        items = self._parse_items_from_json(result)
        models = [pydantic_model.model_validate(i) for i in items]
        return models
