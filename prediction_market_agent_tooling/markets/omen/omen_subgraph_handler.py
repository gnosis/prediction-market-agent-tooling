import sys
import typing as t
from datetime import datetime

import subgrounds.subgraph
from subgrounds import Subgrounds

from prediction_market_agent_tooling.gtypes import HexAddress
from prediction_market_agent_tooling.markets.agent_market import SortBy, FilterBy
from prediction_market_agent_tooling.markets.omen.data_models import (
    OmenMarket,
    OMEN_TRUE_OUTCOME,
    OMEN_FALSE_OUTCOME,
)
from prediction_market_agent_tooling.tools.utils import to_int_timestamp


class OmenSubgraphHandler:
    OMEN_TRADES_SUBGRAPH = "https://api.thegraph.com/subgraphs/name/protofire/omen-xdai"

    def __init__(self):
        self.sg = Subgrounds()
        # Load the subgraph
        self.subgraph = self.sg.load_subgraph(self.OMEN_TRADES_SUBGRAPH)

    def _get_fields_for_markets(self, markets: any):
        # In theory it's possible to store the subgraph schema locally (see https://github.com/0xPlaygrounds/subgrounds/issues/41).
        # Since it's still not working, we hardcode the schema to be fetched below.
        return [
            markets.id,
            markets.title,
            markets.collateralVolume,
            markets.usdVolume,
            markets.collateralToken,
            markets.outcomes,
            markets.outcomeTokenAmounts,
            markets.outcomeTokenMarginalPrices,
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

    def _build_where_statements(
        self,
        filter_by: FilterBy,
        creator: t.Optional[HexAddress] = None,
        outcomes=[OMEN_TRUE_OUTCOME, OMEN_FALSE_OUTCOME],
        created_after: t.Optional[datetime] = None,
    ) -> t.List[subgrounds.subgraph.Filter]:
        # ToDo
        fpmm = self.subgraph.FixedProductMarketMaker  # type: ignore
        where_stms = [
            fpmm.isPendingArbitration == False,
            fpmm.outcomes == outcomes,
        ]

        if creator:
            where_stms.append(fpmm.creator == creator)

        if created_after:
            where_stms.append(fpmm.creationTimestamp > to_int_timestamp(created_after))

        if filter_by == FilterBy.RESOLVED:
            # We can improve this with a is not None filter, when available.
            where_stms.append(fpmm.resolutionTimestamp > 0)
        elif filter_by == FilterBy.OPEN:
            # ToDo - fix hacky way below of filtering markets with answerFinalizedTimestamp is None.
            # We are waiting for the fix on https://github.com/0xPlaygrounds/subgrounds/issues/50
            # where_stms.append(fpmm.answerFinalizedTimestamp is None)
            pass

        return where_stms

    def _build_sort_direction(self, sort_by: SortBy) -> str:
        sort_direction = "asc"
        match sort_by:
            case SortBy.NEWEST:
                sort_direction = "desc"
            case _:
                pass

        return sort_direction

    def get_omen_markets(
        self,
        limit: int,
        sort_by: SortBy,
        filter_by: FilterBy,
        created_after: t.Optional[datetime] = None,
        creator: t.Optional[HexAddress] = None,
        excluded_questions: set[str] | None = None,
        outcomes=[OMEN_TRUE_OUTCOME, OMEN_FALSE_OUTCOME],
    ) -> t.List[OmenMarket]:
        """
        Fetches Omen markets according to filters.
        Limitations:
            - Filters of type "columnA is None" or "columnB is not None" not yet supported - see https://github.com/0xPlaygrounds/subgrounds/issues/50
            - Due to the above problem, we neglect parameter `first` in the query and, instead, return a subset of the items retrieved. This is
            suboptimal but still delivers acceptable performance (~10s for an average market query).
        """

        where_stms = self._build_where_statements(
            filter_by=filter_by,
            creator=creator,
            outcomes=outcomes,
            created_after=created_after,
        )

        sort_direction = self._build_sort_direction(sort_by)

        markets = self.subgraph.Query.fixedProductMarketMakers(  # type: ignore
            orderBy=self.subgraph.FixedProductMarketMaker.creationTimestamp,  # type: ignore
            orderDirection=sort_direction,
            first=sys.maxsize,  # we fetch all possible entries due to filter is None problems (described in function documentation)
            where=where_stms,
        )

        fields = self._get_fields_for_markets(markets)
        result: t.List[dict] = self.sg.query_json(fields)
        items = self._parse_results_from_json(result)
        omen_markets = self._parse_omen_markets_from_list(items)

        if filter_by == FilterBy.OPEN:
            omen_markets = [market for market in omen_markets if market.is_open]

        if not excluded_questions:
            return omen_markets[:limit]
        else:
            return list(
                filter(lambda m: m.question not in excluded_questions, omen_markets)
            )[:limit]

    def get_omen_market(self, market_id: HexAddress) -> OmenMarket:
        markets = self.subgraph.Query.fixedProductMarketMaker(id=market_id)  # type: ignore
        fields = self._get_fields_for_markets(markets)
        result: t.List[dict] = self.sg.query_json(fields)
        items = self._parse_results_from_json(result)
        omen_markets = self._parse_omen_markets_from_list(items)

        if len(omen_markets) > 1:
            raise ValueError(
                f"Fetched wrong number of markets. Expected 1 but got {len(omen_markets)}"
            )

        return omen_markets[0]

    def _parse_results_from_json(self, result: any) -> t.List[dict]:
        """subgrounds return a weird key as a dict key"""
        items = []
        for result_chunk in result:
            for k, v in result_chunk.items():
                # subgrounds might pack all items as a list, indexed by a key, or pack it as a dictionary (if one single element)
                if type(v) is dict:
                    items.extend([v])
                else:
                    items.extend(v)
        return items

    def _parse_omen_markets_from_list(
        self, data_models_list: t.List[dict]
    ) -> t.List[OmenMarket]:
        omen_markets = []
        for i, m in enumerate(data_models_list):
            try:
                omen_markets.append(OmenMarket.model_validate(m))
            except Exception as e:
                if m["title"] is None:
                    # Not interested in making predictions for markets with no titles.
                    continue
                print(f"Could not validate market {m} due to exception {e}, skipping.")
        return omen_markets
