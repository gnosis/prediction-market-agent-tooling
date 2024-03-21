import sys
import typing as t
from datetime import datetime
from typing import Any, NoReturn, Optional, Type, TypeVar, cast
from collections.abc import Mapping, Sequence

from pydantic import BaseModel
from subgrounds import Subgrounds, SyntheticField
from prediction_market_agent_tooling.gtypes import HexAddress
from prediction_market_agent_tooling.markets.agent_market import SortBy, FilterBy
from prediction_market_agent_tooling.markets.omen.data_models import (
    OmenMarket,
    OMEN_TRUE_OUTCOME,
    OMEN_FALSE_OUTCOME,
)
from prediction_market_agent_tooling.tools.utils import to_int_timestamp

T = TypeVar("T", bound=BaseModel)  # T can only be an int or subtype of BaseModel


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

    def get_omen_markets(
        self,
        first: int,
        sort_by: SortBy,
        filter_by: FilterBy,
        created_after: t.Optional[datetime] = None,
        creator: t.Optional[HexAddress] = None,
        excluded_questions: set[str] | None = None,
        outcomes=[OMEN_TRUE_OUTCOME, OMEN_FALSE_OUTCOME],
    ) -> t.List[OmenMarket]:
        fpmm = self.subgraph.FixedProductMarketMaker  # type: ignore
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

        where_stms = [fpmm.isPendingArbitration == False, fpmm.outcomes == outcomes]

        if creator:
            where_stms.append(fpmm.creator == creator)

        if created_after:
            where_stms.append(fpmm.creationTimestamp > to_int_timestamp(created_after))

        if filter_by == FilterBy.RESOLVED:
            where_stms.append(fpmm.resolutionTimestamp is not None)
        elif filter_by == FilterBy.OPEN:
            where_stms.append(fpmm.answerFinalizedTimestamp is None)

        orderDirection = "asc"
        match sort_by:
            case SortBy.NEWEST:
                orderDirection = "desc"
            case _:
                pass

        markets = self.subgraph.Query.fixedProductMarketMakers(  # type: ignore
            orderBy=self.subgraph.FixedProductMarketMaker.creationTimestamp,  # type: ignore
            orderDirection=orderDirection,
            first=first if first else sys.maxsize,
            # where=where_stms,
        )

        fields = self._get_fields_for_markets(markets)
        result: t.List[dict] = self.sg.query_json(fields)
        # subgrounds return a weird key as a dict key
        items = []
        for result_chunk in result:
            for k, v in result_chunk.items():
                items.extend(v)
        # json_result_key = list(result[0].keys())[0]
        # items = result[0][json_result_key]
        for i, market in items:
            try:
                markets.append(OmenMarket.model_validate(m))
            except Exception as e:
                print("ops")
        # markets = [OmenMarket.model_validate(m) for m in items]
        if not excluded_questions:
            return markets
        else:
            return list(filter(lambda m: m.question not in excluded_questions, markets))
