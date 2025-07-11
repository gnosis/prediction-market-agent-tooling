from pydantic import BaseModel

from prediction_market_agent_tooling.gtypes import HexBytes
from prediction_market_agent_tooling.markets.base_subgraph_handler import (
    BaseSubgraphHandler,
)


class ConditionSubgraphModel(BaseModel):
    id: HexBytes
    payoutDenominator: int | None = None
    payoutNumerators: list[int] | None = None
    outcomeSlotCount: int
    resolutionTimestamp: int | None = None


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
        where_stms = {"id_in": [i.hex() for i in condition_ids]}
        conditions = self.conditions_subgraph.Query.conditions(
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
