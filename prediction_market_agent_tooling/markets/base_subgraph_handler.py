import typing as t

import httpx
import tenacity
from pydantic import BaseModel

from prediction_market_agent_tooling.config import APIKeys
from prediction_market_agent_tooling.loggers import logger
from prediction_market_agent_tooling.tools._generic_value import _GenericValue
from prediction_market_agent_tooling.tools.singleton import SingletonMeta

T = t.TypeVar("T", bound=BaseModel)

# The Graph protocol limits
GRAPH_QUERY_LIMIT = 1000


def _value_to_graphql(value: t.Any) -> str:
    """Convert a Python value to a GraphQL literal string."""
    if value is None:
        return "null"
    if isinstance(value, _GenericValue):
        return _value_to_graphql(value.value)
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        return str(value)
    if isinstance(value, str):
        # Escape backslashes and double quotes in string values
        escaped = value.replace("\\", "\\\\").replace('"', '\\"')
        return f'"{escaped}"'
    if isinstance(value, list):
        items = ", ".join(_value_to_graphql(v) for v in value)
        return f"[{items}]"
    if isinstance(value, dict):
        return _dict_to_graphql(value)
    # Fallback: treat as string
    return f'"{value}"'


def _dict_to_graphql(d: dict[str, t.Any]) -> str:
    """Convert a Python dict to a GraphQL object literal."""
    parts = []
    for key, val in d.items():
        parts.append(f"{key}: {_value_to_graphql(val)}")
    return "{" + ", ".join(parts) + "}"


class BaseSubgraphHandler(metaclass=SingletonMeta):
    def __init__(self, timeout: int = 30) -> None:
        self._client = httpx.Client(timeout=timeout)
        self.keys = APIKeys()

    @tenacity.retry(
        stop=tenacity.stop_after_attempt(5),
        wait=tenacity.wait_exponential(multiplier=1, max=10),
        after=lambda retry_state: logger.debug(
            f"Subgraph query failed, attempt {retry_state.attempt_number}."
        ),
    )
    def _execute_query(self, url: str, query: str) -> dict[str, t.Any]:
        """Execute a GraphQL query against a subgraph endpoint."""
        response = self._client.post(url, json={"query": query})
        response.raise_for_status()
        result = response.json()
        if "errors" in result:
            raise RuntimeError(f"GraphQL errors: {result['errors']}")
        return result["data"]

    @staticmethod
    def _build_query(
        entity: str,
        fields: str,
        first: int | None = None,
        skip: int = 0,
        where: dict[str, t.Any] | None = None,
        order_by: str | None = None,
        order_direction: str | None = None,
        block: dict[str, t.Any] | None = None,
        entity_id: str | None = None,
    ) -> str:
        """Build a GraphQL query string."""
        args: list[str] = []
        if entity_id is not None:
            args.append(f'id: "{entity_id}"')
        if first is not None:
            args.append(f"first: {first}")
        if skip > 0:
            args.append(f"skip: {skip}")
        if where:
            args.append(f"where: {_dict_to_graphql(where)}")
        if order_by:
            args.append(f"orderBy: {order_by}")
        if order_direction:
            args.append(f"orderDirection: {order_direction}")
        if block:
            args.append(f"block: {_dict_to_graphql(block)}")

        args_str = f"({', '.join(args)})" if args else ""
        return f"{{ {entity}{args_str} {{ {fields} }} }}"

    def query_subgraph(
        self,
        url: str,
        entity: str,
        fields: str,
        where: dict[str, t.Any] | None = None,
        first: int | None = None,
        order_by: str | None = None,
        order_direction: str | None = None,
        block: dict[str, t.Any] | None = None,
        entity_id: str | None = None,
    ) -> list[dict[str, t.Any]]:
        """Query a subgraph with automatic pagination for large result sets."""
        # Single-entity query (by ID)
        if entity_id is not None:
            query = self._build_query(
                entity=entity,
                fields=fields,
                entity_id=entity_id,
                block=block,
            )
            data = self._execute_query(url, query)
            item = data.get(entity)
            return [item] if item else []

        # Collection query with automatic pagination
        requested = first if first is not None else float("inf")
        all_items: list[dict[str, t.Any]] = []
        skip = 0

        while len(all_items) < requested:
            batch_size = min(GRAPH_QUERY_LIMIT, int(requested - len(all_items)))
            query = self._build_query(
                entity=entity,
                fields=fields,
                first=batch_size,
                skip=skip,
                where=where,
                order_by=order_by,
                order_direction=order_direction,
                block=block,
            )
            data = self._execute_query(url, query)
            items = data.get(entity, [])
            if not items:
                break
            all_items.extend(items)
            if len(items) < batch_size:
                break  # Last page
            skip += len(items)

        return all_items

    def do_query(
        self,
        url: str,
        entity: str,
        fields: str,
        pydantic_model: t.Type[T],
        where: dict[str, t.Any] | None = None,
        first: int | None = None,
        order_by: str | None = None,
        order_direction: str | None = None,
        block: dict[str, t.Any] | None = None,
        entity_id: str | None = None,
    ) -> list[T]:
        """Query a subgraph and parse results into pydantic models."""
        items = self.query_subgraph(
            url=url,
            entity=entity,
            fields=fields,
            where=where,
            first=first,
            order_by=order_by,
            order_direction=order_direction,
            block=block,
            entity_id=entity_id,
        )
        return [pydantic_model.model_validate(i) for i in items]
