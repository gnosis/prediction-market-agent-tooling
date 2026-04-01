from pydantic import BaseModel

from prediction_market_agent_tooling.gtypes import ChecksumAddress, HexBytes
from prediction_market_agent_tooling.markets.base_subgraph_handler import (
    BaseSubgraphHandler,
)
from prediction_market_agent_tooling.markets.polymarket.constants import (
    POLYMARKET_CONDITIONS_SUBGRAPH_URL,
)


class ConditionSubgraphModel(BaseModel):
    id: HexBytes
    payoutDenominator: int | None = None
    payoutNumerators: list[int] | None = None
    outcomeSlotCount: int
    resolutionTimestamp: int | None = None
    questionId: HexBytes

    @property
    def index_sets(self) -> list[int]:
        return [i + 1 for i in range(self.outcomeSlotCount)]


class MarketPositionMarket(BaseModel):
    condition: ConditionSubgraphModel


class MarketPosition(BaseModel):
    id: HexBytes
    market: MarketPositionMarket


CONDITION_FIELDS = (
    "id questionId payoutNumerators payoutDenominator outcomeSlotCount resolutionTimestamp"
)

MARKET_POSITION_FIELDS = (
    f"id market {{ condition {{ {CONDITION_FIELDS} }} }}"
)


class PolymarketSubgraphHandler(BaseSubgraphHandler):
    def __init__(self) -> None:
        super().__init__()

        self.conditions_subgraph_url = POLYMARKET_CONDITIONS_SUBGRAPH_URL.format(
            graph_api_key=self.keys.graph_api_key.get_secret_value()
        )

    def get_conditions(
        self, condition_ids: list[HexBytes]
    ) -> list[ConditionSubgraphModel]:
        where_stms = {"id_in": [i.to_0x_hex() for i in condition_ids]}
        return self.do_query(
            url=self.conditions_subgraph_url,
            entity="conditions",
            fields=CONDITION_FIELDS,
            pydantic_model=ConditionSubgraphModel,
            where=where_stms,
            first=len(condition_ids),
        )

    def get_market_positions_from_user(
        self,
        user: ChecksumAddress,
        first: int = 1000,
        block_number: int | None = None,
    ) -> list[MarketPosition]:
        # Limitation: Cannot filter by market_.condition at subgraph level (indexer error).
        # This fetches ALL positions for the user (up to `first`), and callers must
        # filter by condition_id client-side (see polymarket.py get_position()).
        where_stms = {"user": user.lower()}
        block = {"number": block_number} if block_number else None

        return self.do_query(
            url=self.conditions_subgraph_url,
            entity="marketPositions",
            fields=MARKET_POSITION_FIELDS,
            pydantic_model=MarketPosition,
            where=where_stms,
            first=first,
            block=block,
        )
