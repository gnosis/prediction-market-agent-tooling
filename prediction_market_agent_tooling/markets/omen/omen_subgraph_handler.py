import sys
import typing as t
from datetime import datetime

import tenacity
from eth_typing import ChecksumAddress
from subgrounds import FieldPath, Subgrounds

from prediction_market_agent_tooling.gtypes import HexAddress, HexBytes, Wei, wei_type
from prediction_market_agent_tooling.loggers.loggers import logger
from prediction_market_agent_tooling.markets.agent_market import FilterBy, SortBy
from prediction_market_agent_tooling.markets.omen.data_models import (
    OMEN_FALSE_OUTCOME,
    OMEN_TRUE_OUTCOME,
    OmenBet,
    OmenMarket,
    OmenPosition,
    OmenUserPosition,
    RealityAnswer,
    RealityQuestion,
)
from prediction_market_agent_tooling.tools.singleton import SingletonMeta
from prediction_market_agent_tooling.tools.utils import to_int_timestamp, utcnow
from prediction_market_agent_tooling.tools.web3_utils import ZERO_BYTES


class OmenSubgraphHandler(metaclass=SingletonMeta):
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

        # Patch the query_json method to retry on failure.
        self.sg.query_json = tenacity.retry(
            stop=tenacity.stop_after_attempt(3),
            wait=tenacity.wait_fixed(1),
            after=lambda x: logger.debug(f"query_json failed, {x.attempt_number=}."),
        )(self.sg.query_json)

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

    def _get_fields_for_reality_questions(
        self, questions_field: FieldPath
    ) -> list[FieldPath]:
        # Note: Fields available on the Omen's subgraph Question are different from the Reality's subgraph Question.
        return [
            questions_field.id,
            questions_field.user,
            questions_field.updatedTimestamp,
            questions_field.questionId,
            questions_field.contentHash,
            questions_field.historyHash,
        ]

    def _get_fields_for_answers(self, answers_field: FieldPath) -> list[FieldPath]:
        return [
            answers_field.id,
            answers_field.answer,
            answers_field.bondAggregate,
            answers_field.lastBond,
            answers_field.timestamp,
            answers_field.createdBlock,
        ] + self._get_fields_for_reality_questions(answers_field.question)

    def _get_fields_for_market_questions(
        self, questions_field: FieldPath
    ) -> list[FieldPath]:
        # Note: Fields available on the Omen's subgraph Question are different from the Reality's subgraph Question.
        return [
            questions_field.id,
            questions_field.title,
            questions_field.outcomes,
            questions_field.answerFinalizedTimestamp,
            questions_field.currentAnswer,
            questions_field.data,
            questions_field.templateId,
            questions_field.isPendingArbitration,
            questions_field.openingTimestamp,
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
            markets_field.liquidityParameter,
            markets_field.collateralToken,
            markets_field.outcomes,
            markets_field.outcomeTokenAmounts,
            markets_field.outcomeTokenMarginalPrices,
            markets_field.lastActiveDay,
            markets_field.lastActiveHour,
            markets_field.fee,
            markets_field.answerFinalizedTimestamp,
            markets_field.resolutionTimestamp,
            markets_field.currentAnswer,
            markets_field.creationTimestamp,
            markets_field.category,
            markets_field.condition.id,
            markets_field.condition.outcomeSlotCount,
        ] + self._get_fields_for_market_questions(markets_field.question)

    def _build_where_statements(
        self,
        creator: t.Optional[HexAddress] = None,
        outcomes: list[str] = [OMEN_TRUE_OUTCOME, OMEN_FALSE_OUTCOME],
        created_after: t.Optional[datetime] = None,
        opened_before: t.Optional[datetime] = None,
        opened_after: t.Optional[datetime] = None,
        finalized_before: t.Optional[datetime] = None,
        finalized: bool | None = None,
        resolved: bool | None = None,
        liquidity_bigger_than: Wei | None = None,
        condition_id_in: list[HexBytes] | None = None,
        excluded_questions: set[str] | None = None,
    ) -> dict[str, t.Any]:
        where_stms: dict[str, t.Any] = {
            "isPendingArbitration": False,
            "outcomes": outcomes,
            "title_not": None,
            "question_": {},
            "condition_": {},
        }

        if creator:
            where_stms["creator"] = creator

        if created_after:
            where_stms["creationTimestamp_gt"] = to_int_timestamp(created_after)

        if opened_before:
            where_stms["question_"]["openingTimestamp_lt"] = to_int_timestamp(
                opened_before
            )

        if liquidity_bigger_than is not None:
            where_stms["liquidityParameter_gt"] = liquidity_bigger_than

        if condition_id_in is not None:
            where_stms["condition_"]["id_in"] = [x.hex() for x in condition_id_in]

        if resolved is not None:
            if resolved:
                where_stms["resolutionTimestamp_not"] = None
                where_stms["currentAnswer_not"] = self.INVALID_ANSWER
            else:
                where_stms["resolutionTimestamp"] = None

        if finalized is not None:
            if finalized:
                where_stms["answerFinalizedTimestamp_not"] = None
            else:
                where_stms["answerFinalizedTimestamp"] = None

        if opened_after:
            where_stms["question_"]["openingTimestamp_gt"] = to_int_timestamp(
                opened_after
            )

        if finalized_before:
            where_stms["answerFinalizedTimestamp_lt"] = to_int_timestamp(
                finalized_before
            )

        excluded_question_titles = [""]
        if excluded_questions is not None:
            excluded_question_titles = [i for i in excluded_questions]

        where_stms["question_"]["title_not_in"] = excluded_question_titles
        return where_stms

    def _build_sort_params(
        self, sort_by: SortBy
    ) -> tuple[str | None, FieldPath | None]:
        sort_direction: str | None
        sort_by_field: FieldPath | None

        match sort_by:
            case SortBy.NEWEST:
                sort_direction = "desc"
                sort_by_field = (
                    self.trades_subgraph.FixedProductMarketMaker.creationTimestamp
                )
            case SortBy.CLOSING_SOONEST:
                sort_direction = "asc"
                sort_by_field = (
                    self.trades_subgraph.FixedProductMarketMaker.openingTimestamp
                )
            case SortBy.NONE:
                sort_direction = None
                sort_by_field = None
            case _:
                raise ValueError(f"Unknown sort_by: {sort_by}")

        return sort_direction, sort_by_field

    def get_omen_binary_markets_simple(
        self,
        limit: t.Optional[int],
        # Enumerated values for simpler usage.
        filter_by: FilterBy,
        sort_by: SortBy,
        # Additional filters, these can not be modified by the enums above.
        created_after: datetime | None = None,
        excluded_questions: set[str] | None = None,  # question titles
    ) -> t.List[OmenMarket]:
        """
        Simplified `get_omen_binary_markets` method, which allows to fetch markets based on the filter_by and sort_by values.
        """
        # These values need to be set according to the filter_by value, so they can not be passed as arguments.
        finalized: bool | None = None
        resolved: bool | None = None
        opened_after: datetime | None = None
        liquidity_bigger_than: Wei | None = None

        if filter_by == FilterBy.RESOLVED:
            finalized = True
            resolved = True
        elif filter_by == FilterBy.OPEN:
            # We can not use `resolved=False` + `finalized=False` here,
            # because even closed markets don't need to be resolved yet (e.g. if someone forgot to finalize the question on reality).
            opened_after = utcnow()
            # Even if the market isn't closed yet, liquidity can be withdrawn to 0, which essentially closes the market.
            liquidity_bigger_than = wei_type(0)
        elif filter_by == FilterBy.NONE:
            pass
        else:
            raise ValueError(f"Unknown filter_by: {filter_by}")

        sort_direction, sort_by_field = self._build_sort_params(sort_by)

        return self.get_omen_binary_markets(
            limit=limit,
            finalized=finalized,
            resolved=resolved,
            opened_after=opened_after,
            liquidity_bigger_than=liquidity_bigger_than,
            sort_direction=sort_direction,
            sort_by_field=sort_by_field,
            created_after=created_after,
            excluded_questions=excluded_questions,
        )

    def get_omen_binary_markets(
        self,
        limit: t.Optional[int],
        created_after: t.Optional[datetime] = None,
        opened_before: t.Optional[datetime] = None,
        opened_after: t.Optional[datetime] = None,
        finalized_before: t.Optional[datetime] = None,
        finalized: bool | None = None,
        resolved: bool | None = None,
        creator: t.Optional[HexAddress] = None,
        liquidity_bigger_than: Wei | None = None,
        condition_id_in: list[HexBytes] | None = None,
        excluded_questions: set[str] | None = None,  # question titles
        sort_by_field: FieldPath | None = None,
        sort_direction: str | None = None,
        outcomes: list[str] = [OMEN_TRUE_OUTCOME, OMEN_FALSE_OUTCOME],
    ) -> t.List[OmenMarket]:
        """
        Complete method to fetch Omen binary markets with various filters, use `get_omen_binary_markets_simple` for simplified version that uses FilterBy and SortBy enums.
        """
        where_stms = self._build_where_statements(
            creator=creator,
            outcomes=outcomes,
            created_after=created_after,
            opened_before=opened_before,
            opened_after=opened_after,
            finalized_before=finalized_before,
            finalized=finalized,
            resolved=resolved,
            condition_id_in=condition_id_in,
            excluded_questions=excluded_questions,
            liquidity_bigger_than=liquidity_bigger_than,
        )

        # These values can not be set to `None`, but they can be omitted.
        optional_params = {}
        if sort_by_field is not None:
            optional_params["orderBy"] = sort_by_field
        if sort_direction is not None:
            optional_params["orderDirection"] = sort_direction

        markets = self.trades_subgraph.Query.fixedProductMarketMakers(
            first=(
                limit if limit else sys.maxsize
            ),  # if not limit, we fetch all possible markets
            where=where_stms,
            **optional_params,
        )

        omen_markets = self.do_markets_query(markets)
        return omen_markets

    def do_markets_query(self, markets: FieldPath) -> list[OmenMarket]:
        fields = self._get_fields_for_markets(markets)
        result = self.sg.query_json(fields)
        items = self._parse_items_from_json(result)
        omen_markets = [OmenMarket.model_validate(i) for i in items]
        return omen_markets

    def get_omen_market_by_market_id(self, market_id: HexAddress) -> OmenMarket:
        markets = self.trades_subgraph.Query.fixedProductMarketMaker(
            id=market_id.lower()
        )

        omen_markets = self.do_markets_query(markets)

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

    def _get_fields_for_user_positions(
        self, user_positions: FieldPath
    ) -> list[FieldPath]:
        return [
            user_positions.id,
            user_positions.balance,
            user_positions.wrappedBalance,
            user_positions.totalBalance,
        ] + self._get_fields_for_positions(user_positions.position)

    def _get_fields_for_positions(self, positions: FieldPath) -> list[FieldPath]:
        return [
            positions.id,
            positions.conditionIds,
            positions.collateralTokenAddress,
            positions.indexSets,
        ]

    def get_positions(
        self,
        condition_id: HexBytes | None = None,
    ) -> list[OmenPosition]:
        where_stms: dict[str, t.Any] = {}

        if condition_id is not None:
            where_stms["conditionIds_contains"] = [condition_id.hex()]

        positions = self.conditional_tokens_subgraph.Query.positions(
            first=sys.maxsize, where=where_stms
        )
        fields = self._get_fields_for_positions(positions)
        result = self.sg.query_json(fields)
        items = self._parse_items_from_json(result)
        return [OmenPosition.model_validate(i) for i in items]

    def get_user_positions(
        self,
        better_address: ChecksumAddress,
        position_id_in: list[HexBytes] | None = None,
        total_balance_bigger_than: Wei | None = None,
    ) -> list[OmenUserPosition]:
        where_stms: dict[str, t.Any] = {
            "user": better_address.lower(),
            "position_": {},
        }

        if total_balance_bigger_than is not None:
            where_stms["totalBalance_gt"] = total_balance_bigger_than

        if position_id_in is not None:
            where_stms["position_"]["positionId_in"] = [x.hex() for x in position_id_in]

        positions = self.conditional_tokens_subgraph.Query.userPositions(
            first=sys.maxsize, where=where_stms
        )
        fields = self._get_fields_for_user_positions(positions)
        result = self.sg.query_json(fields)
        items = self._parse_items_from_json(result)
        return [OmenUserPosition.model_validate(i) for i in items]

    def get_trades(
        self,
        better_address: ChecksumAddress | None = None,
        start_time: datetime | None = None,
        end_time: t.Optional[datetime] = None,
        market_id: t.Optional[ChecksumAddress] = None,
        filter_by_answer_finalized_not_null: bool = False,
        type_: t.Literal["Buy", "Sell"] | None = None,
    ) -> list[OmenBet]:
        if not end_time:
            end_time = utcnow()

        trade = self.trades_subgraph.FpmmTrade
        where_stms = []
        if start_time:
            where_stms.append(trade.creationTimestamp >= to_int_timestamp(start_time))
        if end_time:
            where_stms.append(trade.creationTimestamp <= to_int_timestamp(end_time))
        if type_:
            where_stms.append(trade.type == type_)
        if better_address:
            where_stms.append(trade.creator == better_address.lower())
        if market_id:
            where_stms.append(trade.fpmm == market_id.lower())
        if filter_by_answer_finalized_not_null:
            where_stms.append(trade.fpmm.answerFinalizedTimestamp != None)

        trades = self.trades_subgraph.Query.fpmmTrades(
            first=sys.maxsize, where=where_stms
        )
        fields = self._get_fields_for_bets(trades)
        result = self.sg.query_json(fields)
        items = self._parse_items_from_json(result)
        return [OmenBet.model_validate(i) for i in items]

    def get_bets(
        self,
        better_address: ChecksumAddress | None = None,
        start_time: datetime | None = None,
        end_time: t.Optional[datetime] = None,
        market_id: t.Optional[ChecksumAddress] = None,
        filter_by_answer_finalized_not_null: bool = False,
    ) -> list[OmenBet]:
        return self.get_trades(
            better_address=better_address,
            start_time=start_time,
            end_time=end_time,
            market_id=market_id,
            filter_by_answer_finalized_not_null=filter_by_answer_finalized_not_null,
            type_="Buy",  # We consider `bet` to be only the `Buy` trade types.
        )

    def get_resolved_bets(
        self,
        better_address: ChecksumAddress,
        start_time: datetime,
        end_time: t.Optional[datetime] = None,
        market_id: t.Optional[ChecksumAddress] = None,
    ) -> list[OmenBet]:
        omen_bets = self.get_bets(
            better_address=better_address,
            start_time=start_time,
            end_time=end_time,
            market_id=market_id,
            filter_by_answer_finalized_not_null=True,
        )
        return [b for b in omen_bets if b.fpmm.is_resolved]

    def get_resolved_bets_with_valid_answer(
        self,
        better_address: ChecksumAddress,
        start_time: datetime,
        end_time: t.Optional[datetime] = None,
        market_id: t.Optional[ChecksumAddress] = None,
    ) -> list[OmenBet]:
        bets = self.get_resolved_bets(
            better_address=better_address,
            start_time=start_time,
            end_time=end_time,
            market_id=market_id,
        )
        return [b for b in bets if b.fpmm.is_resolved_with_valid_answer]

    def get_questions(
        self,
        user: HexAddress | None = None,
        claimed: bool | None = None,
        current_answer_before: datetime | None = None,
    ) -> list[RealityQuestion]:
        where_stms: dict[str, t.Any] = {}

        if user is not None:
            where_stms["user"] = user.lower()

        if claimed is not None:
            if claimed:
                where_stms["historyHash"] = ZERO_BYTES.hex()
            else:
                where_stms["historyHash_not"] = ZERO_BYTES.hex()

        if current_answer_before is not None:
            where_stms["currentAnswerTimestamp_lt"] = to_int_timestamp(
                current_answer_before
            )

        questions = self.realityeth_subgraph.Query.questions(where=where_stms)
        fields = self._get_fields_for_reality_questions(questions)
        result = self.sg.query_json(fields)
        items = self._parse_items_from_json(result)
        return [RealityQuestion.model_validate(i) for i in items]

    def get_answers(self, question_id: HexBytes) -> list[RealityAnswer]:
        answer = self.realityeth_subgraph.Answer
        # subgrounds complains if bytes is passed, hence we convert it to HexStr
        where_stms = [
            answer.question.questionId == question_id.hex(),
        ]

        answers = self.realityeth_subgraph.Query.answers(where=where_stms)
        fields = self._get_fields_for_answers(answers)
        result = self.sg.query_json(fields)
        items = self._parse_items_from_json(result)
        return [RealityAnswer.model_validate(i) for i in items]

    def get_markets_from_all_user_positions(
        self, user_positions: list[OmenUserPosition]
    ) -> list[OmenMarket]:
        unique_condition_ids: list[HexBytes] = list(
            set(sum([u.position.conditionIds for u in user_positions], []))
        )
        markets = self.get_omen_binary_markets(
            limit=sys.maxsize, condition_id_in=unique_condition_ids
        )
        return markets

    def get_market_from_user_position(
        self, user_position: OmenUserPosition
    ) -> OmenMarket:
        """Markets and user positions are uniquely connected via condition_ids"""
        condition_ids = user_position.position.conditionIds
        markets = self.get_omen_binary_markets(limit=1, condition_id_in=condition_ids)
        if len(markets) != 1:
            raise ValueError(
                f"Incorrect number of markets fetched {len(markets)}, expected 1."
            )
        return markets[0]
