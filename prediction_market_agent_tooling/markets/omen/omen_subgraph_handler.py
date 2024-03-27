import sys
import typing as t
from datetime import datetime

from eth_typing import ChecksumAddress
from hexbytes import HexBytes
from subgrounds import FieldPath, Subgrounds

from prediction_market_agent_tooling.gtypes import HexAddress
from prediction_market_agent_tooling.markets.agent_market import FilterBy, SortBy
from prediction_market_agent_tooling.markets.omen.data_models import (
    OMEN_FALSE_OUTCOME,
    OMEN_TRUE_OUTCOME,
    OmenBet,
    OmenMarket,
    OmenUserPosition,
    RealityAnswer,
)
from prediction_market_agent_tooling.tools.utils import to_int_timestamp, utcnow


class OmenSubgraphHandler:
    """
    Class responsible for handling interactions with Omen subgraphs (trades, conditionalTokens).
    """

    OMEN_TRADES_SUBGRAPH = "https://api.thegraph.com/subgraphs/name/protofire/omen-xdai"
    CONDITIONAL_TOKENS_SUBGRAPH = (
        "https://api.thegraph.com/subgraphs/name/gnosis/conditional-tokens-gc"
    )
    REALITYETH_GRAPH_URL = (
        "https://api.thegraph.com/subgraphs/name/realityeth/realityeth-gnosis"
    )

    INVALID_ANSWER = "ffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffff"

    def __init__(self) -> None:
        self.sg = Subgrounds()
        # Load the subgraph
        self.trades_subgraph = self.sg.load_subgraph(self.OMEN_TRADES_SUBGRAPH)
        self.conditional_tokens_subgraph = self.sg.load_subgraph(
            self.CONDITIONAL_TOKENS_SUBGRAPH
        )
        self.realityeth_subgraph = self.sg.load_subgraph(self.REALITYETH_GRAPH_URL)

    def _get_fields_for_bets(self, bets_field: FieldPath) -> list[FieldPath]:
        markets = bets_field.fpmm
        fields_for_markets = self._get_fields_for_markets(markets)

        fields_for_bets = [
            bets_field.id,
            bets_field.title,
            bets_field.collateralToken,
            bets_field.outcomeTokenMarginalPrice,
            bets_field.oldOutcomeTokenMarginalPrice,
            bets_field.type,
            bets_field.creator.id,
            bets_field.creationTimestamp,
            bets_field.collateralAmount,
            bets_field.collateralAmountUSD,
            bets_field.feeAmount,
            bets_field.outcomeIndex,
            bets_field.outcomeTokensTraded,
            bets_field.transactionHash,
        ]
        return fields_for_bets + fields_for_markets

    def _get_fields_for_answers(self, answers_field: FieldPath) -> list[FieldPath]:
        return [
            answers_field.answer,
            answers_field.question.historyHash,
            answers_field.question.id,
            answers_field.question.user,
            answers_field.question.updatedTimestamp,
            answers_field.question.questionId,
            answers_field.bondAggregate,
            answers_field.lastBond,
            answers_field.timestamp,
        ]

    def _get_fields_for_markets(self, markets_field: FieldPath) -> list[FieldPath]:
        # In theory it's possible to store the subgraph schema locally (see https://github.com/0xPlaygrounds/subgrounds/issues/41).
        # Since it's still not working, we hardcode the schema to be fetched below.
        return [
            markets_field.id,
            markets_field.title,
            markets_field.creator,
            markets_field.collateralVolume,
            markets_field.usdVolume,
            markets_field.collateralToken,
            markets_field.outcomes,
            markets_field.outcomeTokenAmounts,
            markets_field.outcomeTokenMarginalPrices,
            markets_field.fee,
            markets_field.answerFinalizedTimestamp,
            markets_field.resolutionTimestamp,
            markets_field.currentAnswer,
            markets_field.creationTimestamp,
            markets_field.category,
            markets_field.question.id,
            markets_field.question.title,
            markets_field.question.outcomes,
            markets_field.question.answerFinalizedTimestamp,
            markets_field.question.currentAnswer,
            markets_field.condition.id,
            markets_field.condition.outcomeSlotCount,
        ]

    def _build_where_statements(
        self,
        filter_by: FilterBy,
        creator: t.Optional[HexAddress] = None,
        outcomes: list[str] = [OMEN_TRUE_OUTCOME, OMEN_FALSE_OUTCOME],
        created_after: t.Optional[datetime] = None,
        opened_before: t.Optional[datetime] = None,
        excluded_questions: set[str] | None = None,
    ) -> dict[str, t.Any]:
        where_stms: dict[str, t.Any] = {
            "isPendingArbitration": False,
            "outcomes": outcomes,
            "title_not": None,
        }

        if creator:
            where_stms["creator"] = creator

        if created_after:
            where_stms["creationTimestamp_gt"] = to_int_timestamp(created_after)

        if opened_before:
            where_stms["openingTimestamp_gt"] = to_int_timestamp(opened_before)

        where_stms["question_"] = {}
        if filter_by == FilterBy.RESOLVED:
            where_stms["answerFinalizedTimestamp_not"] = None
            where_stms["currentAnswer_not"] = None
            # We cannot add the same type of filter twice, it gets overwritten, hence we use nested filter.
            where_stms["question_"]["currentAnswer_not"] = self.INVALID_ANSWER
        elif filter_by == FilterBy.OPEN:
            where_stms["currentAnswer"] = None

        excluded_question_titles = [""]
        if excluded_questions is not None:
            excluded_question_titles = [i for i in excluded_questions]

        where_stms["question_"]["title_not_in"] = excluded_question_titles
        return where_stms

    def _build_sort_direction(self, sort_by: SortBy) -> str:
        match sort_by:
            case SortBy.NEWEST:
                sort_direction = "desc"
            case SortBy.CLOSING_SOONEST:
                sort_direction = "asc"
            case SortBy.NONE:
                sort_direction = "desc"
            case _:
                raise ValueError(f"Unknown sort_by: {sort_by}")

        return sort_direction

    def get_omen_markets(
        self,
        limit: t.Optional[int],
        sort_by: SortBy,
        filter_by: FilterBy,
        created_after: t.Optional[datetime] = None,
        opened_before: t.Optional[datetime] = None,
        creator: t.Optional[HexAddress] = None,
        excluded_questions: set[str] | None = None,  # question titles
        outcomes: list[str] = [OMEN_TRUE_OUTCOME, OMEN_FALSE_OUTCOME],
    ) -> t.List[OmenMarket]:
        where_stms = self._build_where_statements(
            filter_by=filter_by,
            creator=creator,
            outcomes=outcomes,
            created_after=created_after,
            opened_before=opened_before,
            excluded_questions=excluded_questions,
        )

        sort_direction = self._build_sort_direction(sort_by)
        markets = self.trades_subgraph.Query.fixedProductMarketMakers(
            orderBy=self.trades_subgraph.FixedProductMarketMaker.creationTimestamp,
            orderDirection=sort_direction,
            first=limit
            if limit
            else sys.maxsize,  # if not limit, we fetch all possible markets
            where=where_stms,
        )

        fields = self._get_fields_for_markets(markets)
        result: t.Any = self.sg.query_json(fields)

        items = self._parse_items_from_json(result)
        omen_markets = [OmenMarket.model_validate(i) for i in items]
        return omen_markets

    def get_omen_market(self, market_id: HexAddress) -> OmenMarket:
        markets = self.trades_subgraph.Query.fixedProductMarketMaker(
            id=market_id.lower()
        )
        fields = self._get_fields_for_markets(markets)
        result: t.Any = self.sg.query_json(fields)
        items = self._parse_items_from_json(result)
        omen_markets = [OmenMarket.model_validate(i) for i in items]

        if len(omen_markets) != 1:
            raise ValueError(
                f"Fetched wrong number of markets. Expected 1 but got {len(omen_markets)}"
            )

        return omen_markets[0]

    def _parse_items_from_json(
        self, result: list[dict[str, t.Any]]
    ) -> list[dict[str, t.Any]]:
        """subgrounds return a weird key as a dict key"""
        items = []
        for result_chunk in result:
            for k, v in result_chunk.items():
                # subgrounds might pack all items as a list, indexed by a key, or pack it as a dictionary (if one single element)
                if isinstance(v, dict):
                    items.extend([v])
                else:
                    items.extend(v)
        return items

    def get_user_positions(
        self, better_address: ChecksumAddress
    ) -> list[OmenUserPosition]:
        positions = self.conditional_tokens_subgraph.Query.userPositions(
            first=sys.maxsize,
            where=[
                self.conditional_tokens_subgraph.UserPosition.user
                == better_address.lower()
            ],
        )

        result: t.Any = self.sg.query_json(
            [positions.id, positions.position.id, positions.position.conditionIds]
        )
        items = self._parse_items_from_json(result)
        return [OmenUserPosition.model_validate(i) for i in items]

    def get_bets(
        self,
        better_address: ChecksumAddress,
        start_time: datetime,
        end_time: t.Optional[datetime] = None,
        market_id: t.Optional[str] = None,
        filter_by_answer_finalized_not_null: bool = False,
    ) -> list[OmenBet]:
        if not end_time:
            end_time = utcnow()

        trade = self.trades_subgraph.FpmmTrade
        where_stms = [
            trade.type == "Buy",
            trade.creator == better_address.lower(),
            trade.creationTimestamp >= to_int_timestamp(start_time),
            trade.creationTimestamp <= to_int_timestamp(end_time),
        ]
        if market_id:
            where_stms.append(trade.fpmm == market_id)
        if filter_by_answer_finalized_not_null:
            where_stms.append(trade.fpmm.answerFinalizedTimestamp != None)

        trades = self.trades_subgraph.Query.fpmmTrades(
            first=sys.maxsize, where=where_stms
        )
        fields = self._get_fields_for_bets(trades)
        result: t.Any = self.sg.query_json(fields)
        items = self._parse_items_from_json(result)
        return [OmenBet.model_validate(i) for i in items]

    def get_resolved_bets(
        self,
        better_address: ChecksumAddress,
        start_time: datetime,
        end_time: t.Optional[datetime] = None,
        market_id: t.Optional[str] = None,
    ) -> list[OmenBet]:
        omen_bets = self.get_bets(
            better_address=better_address,
            start_time=start_time,
            end_time=end_time,
            market_id=market_id,
            filter_by_answer_finalized_not_null=True,
        )
        return [b for b in omen_bets if b.fpmm.is_resolved]

    def get_answers(self, question_id: HexBytes) -> list[RealityAnswer]:
        answer = self.realityeth_subgraph.Answer
        # subgrounds complains if bytes is passed, hence we convert it to HexStr
        where_stms = [
            answer.question.questionId == question_id.hex(),
        ]

        answers = self.realityeth_subgraph.Query.answers(where=where_stms)
        fields = self._get_fields_for_answers(answers)
        result: t.Any = self.sg.query_json(fields)
        items = self._parse_items_from_json(result)
        return [RealityAnswer.model_validate(i) for i in items]
