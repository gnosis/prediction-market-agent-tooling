from pydantic import BaseModel
from subgrounds import FieldPath

from prediction_market_agent_tooling.gtypes import ChecksumAddress, HexBytes
from prediction_market_agent_tooling.markets.base_subgraph_handler import (
    BaseSubgraphHandler,
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


class PolymarketSubgraphHandler(BaseSubgraphHandler):
    POLYMARKET_CONDITIONS_SUBGRAPH = "https://gateway.thegraph.com/api/{graph_api_key}/subgraphs/id/81Dm16JjuFSrqz813HysXoUPvzTwE7fsfPk2RTf66nyC"

    def __init__(self) -> None:
        super().__init__()

        # Load the subgraph
        self.conditions_subgraph = self.sg.load_subgraph(
            self.POLYMARKET_CONDITIONS_SUBGRAPH.format(
                graph_api_key=self.keys.graph_api_key.get_secret_value()
            )
        )

    def _get_fields_for_condition(self, field: FieldPath) -> list[FieldPath]:
        return [
            field.id,
            field.questionId,
            field.payoutNumerators,
            field.payoutDenominator,
            field.outcomeSlotCount,
            field.resolutionTimestamp,
        ]

    def get_conditions(
        self, condition_ids: list[HexBytes]
    ) -> list[ConditionSubgraphModel]:
        where_stms = {"id_in": [i.to_0x_hex() for i in condition_ids]}
        conditions = self.conditions_subgraph.Query.conditions(
            first=len(condition_ids),
            where=where_stms,
        )

        condition_fields = self._get_fields_for_condition(conditions)

        conditions_models = self.do_query(
            fields=condition_fields, pydantic_model=ConditionSubgraphModel
        )
        return conditions_models

    def get_market_positions_from_user(
        self,
        user: ChecksumAddress,
        first: int = 1000,
        block_number: int | None = None,
    ) -> list[MarketPosition]:
        # Not possible to filter using `market_.condition` on a subgraph level, bad indexers error.
        positions = self.conditions_subgraph.Query.marketPositions(
            first=first,
            where={"user": user.lower()},
            block={"number": block_number} if block_number else None,
        )

        condition_fields = (
            self._get_fields_for_condition(positions.market.condition) + positions.id
        )

        positions_models = self.do_query(
            fields=condition_fields, pydantic_model=MarketPosition
        )
        return positions_models
