from pydantic import BaseModel

from prediction_market_agent_tooling.gtypes import HexBytes, ChecksumAddress
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

    def get_conditions(
        self, condition_ids: list[HexBytes]
    ) -> list[ConditionSubgraphModel]:
        where_stms = {"id_in": [i.to_0x_hex() for i in condition_ids]}
        conditions = self.conditions_subgraph.Query.conditions(
            first=len(condition_ids),
            where=where_stms,
        )

        condition_fields = [
            conditions.id,
            conditions.payoutNumerators,
            conditions.payoutDenominator,
            conditions.outcomeSlotCount,
            conditions.resolutionTimestamp,
        ]

        conditions_models = self.do_query(
            fields=condition_fields, pydantic_model=ConditionSubgraphModel
        )
        return conditions_models

    def get_market_positions_from_user(
        self,
        user: ChecksumAddress | None = None,
        block_number: int | None = None,  # fetch already redeemed positions
    ) -> list[MarketPosition]:
        # ToDo - remove None option
        positions = self.conditions_subgraph.Query.marketPositions(
            first=1000,
            where={"user": user.lower()} if user else None,
            block={"number": block_number} if block_number else None,
        )

        condition_fields = [
            positions.market.condition.id,
            positions.market.condition.questionId,
            positions.market.condition.payoutNumerators,
            positions.market.condition.payoutDenominator,
            positions.market.condition.outcomeSlotCount,
            positions.market.condition.resolutionTimestamp,
        ]

        positions_models = self.do_query(
            fields=condition_fields, pydantic_model=MarketPosition
        )
        return positions_models
