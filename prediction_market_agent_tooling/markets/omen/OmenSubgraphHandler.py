from datetime import datetime

from eth_typing import HexAddress
from subgrounds import Subgrounds, SyntheticField
import typing as t

from prediction_market_agent_tooling.markets.agent_market import SortBy, FilterBy
from prediction_market_agent_tooling.markets.omen.omen_graph_queries import (
    to_int_timestamp,
)


class OmenSubgraphHandler:
    OMEN_TRADES_SUBGRAPH = "https://api.thegraph.com/subgraphs/name/protofire/omen-xdai"

    def __init__(self):
        self.sg = Subgrounds()
        # Load the subgraph
        self.subgraph = self.sg.load_subgraph(self.OMEN_TRADES_SUBGRAPH)

    def _get_fields_for_markets(self, markets: any):
        return [
            markets.id,
            markets.title,
            markets.collateralVolume,
            markets.usdVolume,
            markets.collateralToken,
            markets.outcomes,
            markets.outcomeTokenAmountsAsStr,
            markets.outcomeTokenMarginalPricesAsStr,
            markets.fee,
            markets.answerFinalizedTimestamp,
            markets.resolutionTimestamp,
            markets.currentAnswer,
            markets.creationTimestamp,
            markets.category,
            markets.question.id,
            markets.question.answerFinalizedTimestamp,
            markets.question.currentAnswer,
            markets.condition.id,
            markets.condition.outcomeSlotCount,
        ]

    def fetch_markets(
        self,
        sort_by: SortBy,
        filter_by: FilterBy,
        creator: t.Optional[HexAddress],
        created_after: t.Optional[datetime] = None,
    ):
        fpmm = self.subgraph.FixedProductMarketMaker  # ignore
        fpmm.outcomeTokenAmountsAsStr = SyntheticField(
            f=lambda x: str(x),
            type_=SyntheticField.STRING,
            deps=fpmm.outcomeTokenAmounts,
        )
        fpmm.outcomeTokenMarginalPricesAsStr = SyntheticField(
            f=lambda x: str(x),
            type_=SyntheticField.STRING,
            deps=fpmm.outcomeTokenMarginalPrices,
        )

        where_stms = [fpmm.isPendingArbitration == False]

        if creator:
            where_stms.append(fpmm.creator == creator)

        if created_after:
            where_stms.append(fpmm.creationTimestamp > to_int_timestamp(created_after))

        if filter_by == FilterBy.RESOLVED:
            where_stms.append(fpmm.resolutionTimestamp is not None)
        elif filter_by == FilterBy.OPEN:
            where_stms.append(fpmm.answerFinalizedTimestamp is None)
        elif filter_by == FilterBy.NONE:
            # don't apply any filters
            pass
        else:
            raise ValueError(f"Unknown filter_by: {filter_by}")

        markets = self.subgraph.Query.fixedProductMarketMakers(
            orderBy=self.subgraph.FixedProductMarketMaker.creationTimestamp,
            orderDirection="desc",
            first=1001,
            where=where_stms,
        )

        fields = self._get_fields_for_markets(markets)
        result: t.List[dict] = self.sg.query_json(fields)
        # We flatten the results
        new_dict = [value for k, v in result]
        models = []
