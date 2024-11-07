import sys
import typing as t

import requests
from PIL import Image
from PIL.Image import Image as ImageType
from subgrounds import FieldPath

from prediction_market_agent_tooling.gtypes import (
    ChecksumAddress,
    HexAddress,
    HexBytes,
    Wei,
    wei_type,
)
from prediction_market_agent_tooling.markets.agent_market import FilterBy, SortBy
from prediction_market_agent_tooling.markets.base_subgraph_handler import (
    BaseSubgraphHandler,
)
from prediction_market_agent_tooling.markets.omen.data_models import (
    OMEN_BINARY_MARKET_OUTCOMES,
    ContractPrediction,
    OmenBet,
    OmenMarket,
    OmenPosition,
    OmenUserPosition,
    RealityAnswer,
    RealityQuestion,
    RealityResponse,
)
from prediction_market_agent_tooling.markets.omen.omen_contracts import (
    OmenThumbnailMapping,
    WrappedxDaiContract,
    sDaiContract,
)
from prediction_market_agent_tooling.tools.utils import (
    DatetimeUTC,
    to_int_timestamp,
    utcnow,
)
from prediction_market_agent_tooling.tools.web3_utils import (
    ZERO_BYTES,
    byte32_to_ipfscidv0,
)

# TODO: Agents don't know how to convert value between other tokens, we assume 1 unit = 1xDai = $1 (for example if market would be in wETH, betting 1 unit of wETH would be crazy :D)
SAFE_COLLATERAL_TOKEN_MARKETS = (
    WrappedxDaiContract().address,
    sDaiContract().address,
)


class OmenSubgraphHandler(BaseSubgraphHandler):
    """
    Class responsible for handling interactions with Omen subgraphs (trades, conditionalTokens).
    """

    OMEN_TRADES_SUBGRAPH = "https://gateway-arbitrum.network.thegraph.com/api/{graph_api_key}/subgraphs/id/9fUVQpFwzpdWS9bq5WkAnmKbNNcoBwatMR4yZq81pbbz"

    CONDITIONAL_TOKENS_SUBGRAPH = "https://gateway-arbitrum.network.thegraph.com/api/{graph_api_key}/subgraphs/id/7s9rGBffUTL8kDZuxvvpuc46v44iuDarbrADBFw5uVp2"

    REALITYETH_GRAPH_URL = "https://gateway-arbitrum.network.thegraph.com/api/{graph_api_key}/subgraphs/id/E7ymrCnNcQdAAgLbdFWzGE5mvr5Mb5T9VfT43FqA7bNh"

    OMEN_IMAGE_MAPPING_GRAPH_URL = "https://gateway-arbitrum.network.thegraph.com/api/{graph_api_key}/subgraphs/id/EWN14ciGK53PpUiKSm7kMWQ6G4iz3tDrRLyZ1iXMQEdu"

    OMEN_AGENT_RESULT_MAPPING_GRAPH_URL = "https://gateway-arbitrum.network.thegraph.com/api/{graph_api_key}/subgraphs/id/J6bJEnbqJpAvNyQE8i58M9mKF4zqo33BEJRdnXmqa6Kn"

    INVALID_ANSWER = "ffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffff"

    def __init__(self) -> None:
        super().__init__()

        # Load the subgraph
        self.trades_subgraph = self.sg.load_subgraph(
            self.OMEN_TRADES_SUBGRAPH.format(
                graph_api_key=self.keys.graph_api_key.get_secret_value()
            )
        )
        self.conditional_tokens_subgraph = self.sg.load_subgraph(
            self.CONDITIONAL_TOKENS_SUBGRAPH.format(
                graph_api_key=self.keys.graph_api_key.get_secret_value()
            )
        )
        self.realityeth_subgraph = self.sg.load_subgraph(
            self.REALITYETH_GRAPH_URL.format(
                graph_api_key=self.keys.graph_api_key.get_secret_value()
            )
        )
        self.omen_image_mapping_subgraph = self.sg.load_subgraph(
            self.OMEN_IMAGE_MAPPING_GRAPH_URL.format(
                graph_api_key=self.keys.graph_api_key.get_secret_value()
            )
        )

        self.omen_agent_result_mapping_subgraph = self.sg.load_subgraph(
            self.OMEN_AGENT_RESULT_MAPPING_GRAPH_URL.format(
                graph_api_key=self.keys.graph_api_key.get_secret_value()
            )
        )

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
            questions_field.answerFinalizedTimestamp,
            questions_field.currentScheduledFinalizationTimestamp,
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

    def _get_fields_for_responses(self, responses_field: FieldPath) -> list[FieldPath]:
        return [
            responses_field.id,
            responses_field.timestamp,
            responses_field.answer,
            responses_field.isUnrevealed,
            responses_field.isCommitment,
            responses_field.bond,
            responses_field.user,
            responses_field.historyHash,
            responses_field.createdBlock,
            responses_field.revealedBlock,
        ] + self._get_fields_for_reality_questions(responses_field.question)

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
        creator: HexAddress | None,
        creator_in: t.Sequence[HexAddress] | None,
        outcomes: list[str],
        created_after: DatetimeUTC | None,
        question_opened_before: DatetimeUTC | None,
        question_opened_after: DatetimeUTC | None,
        question_finalized_before: DatetimeUTC | None,
        question_finalized_after: DatetimeUTC | None,
        question_with_answers: bool | None,
        question_id: HexBytes | None,
        question_id_in: list[HexBytes] | None,
        question_current_answer_before: DatetimeUTC | None,
        question_excluded_titles: set[str] | None,
        resolved: bool | None,
        liquidity_bigger_than: Wei | None,
        condition_id_in: list[HexBytes] | None,
        id_in: list[str] | None,
        collateral_token_address_in: tuple[ChecksumAddress, ...] | None,
        category: str | None,
    ) -> dict[str, t.Any]:
        where_stms: dict[str, t.Any] = {
            "isPendingArbitration": False,
            "outcomes": outcomes,
            "title_not": None,
            "condition_": {},
        }

        where_stms["question_"] = self.get_omen_question_filters(
            question_id=question_id,
            opened_before=question_opened_before,
            opened_after=question_opened_after,
            finalized_before=question_finalized_before,
            finalized_after=question_finalized_after,
            with_answers=question_with_answers,
            current_answer_before=question_current_answer_before,
            question_id_in=question_id_in,
            excluded_titles=question_excluded_titles,
        )

        if collateral_token_address_in:
            where_stms["collateralToken_in"] = [
                x.lower() for x in collateral_token_address_in
            ]

        if creator:
            where_stms["creator"] = creator.lower()

        if creator_in:
            where_stms["creator_in"] = [x.lower() for x in creator_in]

        if created_after:
            where_stms["creationTimestamp_gt"] = to_int_timestamp(created_after)

        if liquidity_bigger_than is not None:
            where_stms["liquidityParameter_gt"] = liquidity_bigger_than

        if condition_id_in is not None:
            where_stms["condition_"]["id_in"] = [x.hex() for x in condition_id_in]

        if id_in is not None:
            where_stms["id_in"] = [i.lower() for i in id_in]

        if resolved is not None:
            if resolved:
                where_stms["resolutionTimestamp_not"] = None
                where_stms["currentAnswer_not"] = self.INVALID_ANSWER
            else:
                where_stms["resolutionTimestamp"] = None

        if category:
            where_stms["category"] = category

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
            case SortBy.HIGHEST_LIQUIDITY:
                sort_direction = "desc"
                sort_by_field = (
                    self.trades_subgraph.FixedProductMarketMaker.liquidityMeasure
                )
            case SortBy.LOWEST_LIQUIDITY:
                sort_direction = "asc"
                sort_by_field = (
                    self.trades_subgraph.FixedProductMarketMaker.liquidityMeasure
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
        created_after: DatetimeUTC | None = None,
        excluded_questions: set[str] | None = None,  # question titles
        collateral_token_address_in: (
            tuple[ChecksumAddress, ...] | None
        ) = SAFE_COLLATERAL_TOKEN_MARKETS,
        category: str | None = None,
        creator_in: t.Sequence[HexAddress] | None = None,
    ) -> t.List[OmenMarket]:
        """
        Simplified `get_omen_binary_markets` method, which allows to fetch markets based on the filter_by and sort_by values.
        """
        # These values need to be set according to the filter_by value, so they can not be passed as arguments.
        resolved: bool | None = None
        opened_after: DatetimeUTC | None = None
        liquidity_bigger_than: Wei | None = None

        if filter_by == FilterBy.RESOLVED:
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
            resolved=resolved,
            question_opened_after=opened_after,
            liquidity_bigger_than=liquidity_bigger_than,
            sort_direction=sort_direction,
            sort_by_field=sort_by_field,
            created_after=created_after,
            question_excluded_titles=excluded_questions,
            collateral_token_address_in=collateral_token_address_in,
            category=category,
            creator_in=creator_in,
        )

    def get_omen_binary_markets(
        self,
        limit: t.Optional[int],
        creator: HexAddress | None = None,
        creator_in: t.Sequence[HexAddress] | None = None,
        created_after: DatetimeUTC | None = None,
        question_opened_before: DatetimeUTC | None = None,
        question_opened_after: DatetimeUTC | None = None,
        question_finalized_before: DatetimeUTC | None = None,
        question_finalized_after: DatetimeUTC | None = None,
        question_with_answers: bool | None = None,
        question_id: HexBytes | None = None,
        question_id_in: list[HexBytes] | None = None,
        question_current_answer_before: DatetimeUTC | None = None,
        question_excluded_titles: set[str] | None = None,
        resolved: bool | None = None,
        liquidity_bigger_than: Wei | None = None,
        condition_id_in: list[HexBytes] | None = None,
        id_in: list[str] | None = None,
        sort_by_field: FieldPath | None = None,
        sort_direction: str | None = None,
        outcomes: list[str] = OMEN_BINARY_MARKET_OUTCOMES,
        collateral_token_address_in: (
            tuple[ChecksumAddress, ...] | None
        ) = SAFE_COLLATERAL_TOKEN_MARKETS,
        category: str | None = None,
    ) -> t.List[OmenMarket]:
        """
        Complete method to fetch Omen binary markets with various filters, use `get_omen_binary_markets_simple` for simplified version that uses FilterBy and SortBy enums.
        """
        where_stms = self._build_where_statements(
            creator=creator,
            creator_in=creator_in,
            outcomes=outcomes,
            created_after=created_after,
            question_opened_before=question_opened_before,
            question_opened_after=question_opened_after,
            question_finalized_before=question_finalized_before,
            question_finalized_after=question_finalized_after,
            question_with_answers=question_with_answers,
            question_id=question_id,
            question_id_in=question_id_in,
            question_current_answer_before=question_current_answer_before,
            question_excluded_titles=question_excluded_titles,
            resolved=resolved,
            condition_id_in=condition_id_in,
            id_in=id_in,
            liquidity_bigger_than=liquidity_bigger_than,
            collateral_token_address_in=collateral_token_address_in,
            category=category,
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

        fields = self._get_fields_for_markets(markets)
        omen_markets = self.do_query(fields=fields, pydantic_model=OmenMarket)
        return omen_markets

    def get_omen_market_by_market_id(
        self, market_id: HexAddress, block_number: int | None = None
    ) -> OmenMarket:
        query_filters: dict[str, t.Any] = {"id": market_id.lower()}
        if block_number:
            query_filters["block"] = {"number": block_number}

        markets = self.trades_subgraph.Query.fixedProductMarketMaker(**query_filters)

        fields = self._get_fields_for_markets(markets)
        omen_markets = self.do_query(fields=fields, pydantic_model=OmenMarket)

        if len(omen_markets) != 1:
            raise ValueError(
                f"Fetched wrong number of markets. Expected 1 but got {len(omen_markets)}"
            )

        return omen_markets[0]

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
        limit: int | None = None,
        better_address: ChecksumAddress | None = None,
        start_time: DatetimeUTC | None = None,
        end_time: t.Optional[DatetimeUTC] = None,
        market_id: t.Optional[ChecksumAddress] = None,
        filter_by_answer_finalized_not_null: bool = False,
        type_: t.Literal["Buy", "Sell"] | None = None,
        market_opening_after: DatetimeUTC | None = None,
        collateral_amount_more_than: Wei | None = None,
        sort_by_field: FieldPath | None = None,
        sort_direction: str | None = None,
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
        if market_opening_after is not None:
            where_stms.append(
                trade.fpmm.openingTimestamp > to_int_timestamp(market_opening_after)
            )
        if collateral_amount_more_than is not None:
            where_stms.append(trade.collateralAmount > collateral_amount_more_than)

        # These values can not be set to `None`, but they can be omitted.
        optional_params = {}
        if sort_by_field is not None:
            optional_params["orderBy"] = sort_by_field
        if sort_direction is not None:
            optional_params["orderDirection"] = sort_direction

        trades = self.trades_subgraph.Query.fpmmTrades(
            first=limit if limit else sys.maxsize,
            where=where_stms,
            **optional_params,
        )
        fields = self._get_fields_for_bets(trades)
        result = self.sg.query_json(fields)
        items = self._parse_items_from_json(result)
        return [OmenBet.model_validate(i) for i in items]

    def get_bets(
        self,
        better_address: ChecksumAddress | None = None,
        start_time: DatetimeUTC | None = None,
        end_time: t.Optional[DatetimeUTC] = None,
        market_id: t.Optional[ChecksumAddress] = None,
        filter_by_answer_finalized_not_null: bool = False,
        market_opening_after: DatetimeUTC | None = None,
        collateral_amount_more_than: Wei | None = None,
    ) -> list[OmenBet]:
        return self.get_trades(
            better_address=better_address,
            start_time=start_time,
            end_time=end_time,
            market_id=market_id,
            filter_by_answer_finalized_not_null=filter_by_answer_finalized_not_null,
            type_="Buy",  # We consider `bet` to be only the `Buy` trade types.
            market_opening_after=market_opening_after,
            collateral_amount_more_than=collateral_amount_more_than,
        )

    def get_resolved_bets(
        self,
        better_address: ChecksumAddress,
        start_time: DatetimeUTC,
        end_time: t.Optional[DatetimeUTC] = None,
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
        start_time: DatetimeUTC,
        end_time: t.Optional[DatetimeUTC] = None,
        market_id: t.Optional[ChecksumAddress] = None,
    ) -> list[OmenBet]:
        bets = self.get_resolved_bets(
            better_address=better_address,
            start_time=start_time,
            end_time=end_time,
            market_id=market_id,
        )
        return [b for b in bets if b.fpmm.is_resolved_with_valid_answer]

    @staticmethod
    def get_reality_question_filters(
        user: HexAddress | None,
        claimed: bool | None,
        current_answer_before: DatetimeUTC | None,
        finalized_before: DatetimeUTC | None,
        finalized_after: DatetimeUTC | None,
        with_answers: bool | None,
        question_id: HexBytes | None,
        question_id_in: list[HexBytes] | None,
        opened_before: t.Optional[DatetimeUTC],
        opened_after: t.Optional[DatetimeUTC],
        excluded_titles: set[str] | None,
    ) -> dict[str, t.Any]:
        """
        Be aware, both Omen subgraph and Reality subgraph are indexing questions, but their fields are a bit different.
        """
        where_stms: dict[str, t.Any] = {}

        if user is not None:
            where_stms["user"] = user.lower()

        if question_id is not None:
            where_stms["questionId"] = question_id.hex()

        if claimed is not None:
            if claimed:
                where_stms["historyHash"] = ZERO_BYTES.hex()
            else:
                where_stms["historyHash_not"] = ZERO_BYTES.hex()

        if current_answer_before is not None:
            where_stms["currentAnswerTimestamp_lt"] = to_int_timestamp(
                current_answer_before
            )

        if opened_before:
            where_stms["openingTimestamp_lt"] = to_int_timestamp(opened_before)

        if opened_after:
            where_stms["openingTimestamp_gt"] = to_int_timestamp(opened_after)

        if finalized_before is not None:
            where_stms["answerFinalizedTimestamp_lt"] = to_int_timestamp(
                finalized_before
            )

        if finalized_after is not None:
            where_stms["answerFinalizedTimestamp_gt"] = to_int_timestamp(
                finalized_after
            )

        if with_answers is not None:
            if with_answers:
                where_stms["answerFinalizedTimestamp_not"] = None
            else:
                where_stms["answerFinalizedTimestamp"] = None

        if question_id_in is not None:
            # Be aware: On Omen subgraph, question's `id` represents `questionId` on reality subgraph. And `id` on reality subraph is just a weird concat of multiple things from the question.
            where_stms["questionId_in"] = [x.hex() for x in question_id_in]

        if excluded_titles:
            # Be aware: This is called `title_not_in` on Omen subgraph.
            where_stms["qTitle_not_in"] = [i for i in excluded_titles]

        return where_stms

    @staticmethod
    def get_omen_question_filters(
        current_answer_before: DatetimeUTC | None,
        finalized_before: DatetimeUTC | None,
        finalized_after: DatetimeUTC | None,
        with_answers: bool | None,
        question_id: HexBytes | None,
        question_id_in: list[HexBytes] | None,
        opened_before: t.Optional[DatetimeUTC],
        opened_after: t.Optional[DatetimeUTC],
        excluded_titles: set[str] | None,
    ) -> dict[str, t.Any]:
        """
        Be aware, both Omen subgraph and Reality subgraph are indexing questions, but their fields are a bit different.
        """
        where_stms: dict[str, t.Any] = {}

        if question_id is not None:
            where_stms["questionId"] = question_id.hex()

        if current_answer_before is not None:
            where_stms["currentAnswerTimestamp_lt"] = to_int_timestamp(
                current_answer_before
            )

        if opened_before:
            where_stms["openingTimestamp_lt"] = to_int_timestamp(opened_before)

        if opened_after:
            where_stms["openingTimestamp_gt"] = to_int_timestamp(opened_after)

        if finalized_before is not None:
            where_stms["answerFinalizedTimestamp_lt"] = to_int_timestamp(
                finalized_before
            )

        if finalized_after is not None:
            where_stms["answerFinalizedTimestamp_gt"] = to_int_timestamp(
                finalized_after
            )

        if with_answers is not None:
            if with_answers:
                where_stms["answerFinalizedTimestamp_not"] = None
            else:
                where_stms["answerFinalizedTimestamp"] = None

        if question_id_in is not None:
            # Be aware: On Omen subgraph, question's `id` represents `questionId` on reality subgraph. And `id` on reality subraph is just a weird concat of multiple things from the question.
            where_stms["id_in"] = [x.hex() for x in question_id_in]

        if excluded_titles:
            # Be aware: This is called `qTitle_not_in` on Omen subgraph.
            where_stms["title_not_in"] = [i for i in excluded_titles]

        return where_stms

    def get_questions(
        self,
        limit: int | None,
        user: HexAddress | None = None,
        claimed: bool | None = None,
        current_answer_before: DatetimeUTC | None = None,
        finalized_before: DatetimeUTC | None = None,
        finalized_after: DatetimeUTC | None = None,
        with_answers: bool | None = None,
        question_id_in: list[HexBytes] | None = None,
        question_id: HexBytes | None = None,
        opened_before: DatetimeUTC | None = None,
        opened_after: DatetimeUTC | None = None,
        excluded_titles: set[str] | None = None,
    ) -> list[RealityQuestion]:
        where_stms: dict[str, t.Any] = self.get_reality_question_filters(
            user=user,
            claimed=claimed,
            finalized_before=finalized_before,
            finalized_after=finalized_after,
            with_answers=with_answers,
            current_answer_before=current_answer_before,
            question_id_in=question_id_in,
            question_id=question_id,
            opened_before=opened_before,
            opened_after=opened_after,
            excluded_titles=excluded_titles,
        )
        questions = self.realityeth_subgraph.Query.questions(
            first=(
                limit if limit else sys.maxsize
            ),  # if not limit, we fetch all possible
            where=where_stms,
        )
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

    def get_responses(
        self,
        limit: int | None,
        user: HexAddress | None = None,
        question_user: HexAddress | None = None,
        question_claimed: bool | None = None,
        question_opened_before: t.Optional[DatetimeUTC] = None,
        question_opened_after: t.Optional[DatetimeUTC] = None,
        question_finalized_before: t.Optional[DatetimeUTC] = None,
        question_finalized_after: t.Optional[DatetimeUTC] = None,
        question_with_answers: bool | None = None,
        question_id: HexBytes | None = None,
        question_id_in: list[HexBytes] | None = None,
        question_current_answer_before: DatetimeUTC | None = None,
        question_excluded_titles: set[str] | None = None,
    ) -> list[RealityResponse]:
        where_stms: dict[str, t.Any] = {}

        if user is not None:
            where_stms["user"] = user.lower()

        where_stms["question_"] = self.get_reality_question_filters(
            user=question_user,
            question_id=question_id,
            claimed=question_claimed,
            opened_before=question_opened_before,
            opened_after=question_opened_after,
            finalized_before=question_finalized_before,
            finalized_after=question_finalized_after,
            with_answers=question_with_answers,
            current_answer_before=question_current_answer_before,
            question_id_in=question_id_in,
            excluded_titles=question_excluded_titles,
        )

        responses = self.realityeth_subgraph.Query.responses(
            first=(
                limit if limit else sys.maxsize
            ),  # if not limit, we fetch all possible
            where=where_stms,
        )
        fields = self._get_fields_for_responses(responses)
        result = self.sg.query_json(fields)
        items = self._parse_items_from_json(result)
        return [RealityResponse.model_validate(i) for i in items]

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

    def get_market_image_url(self, market_id: HexAddress) -> str | None:
        image = self.omen_image_mapping_subgraph.Query.omenThumbnailMapping(
            id=market_id.lower()
        )
        fields = [image.id, image.image_hash]
        result = self.sg.query_json(fields)
        items = self._parse_items_from_json(result)
        if not items:
            return None
        parsed = byte32_to_ipfscidv0(HexBytes(items[0]["image_hash"]))
        return OmenThumbnailMapping.construct_ipfs_url(parsed)

    def get_market_image(self, market_id: HexAddress) -> ImageType | None:
        image_url = self.get_market_image_url(market_id)
        return (
            Image.open(requests.get(image_url, stream=True).raw)  # type: ignore[arg-type]
            if image_url is not None
            else None
        )

    def get_agent_results_for_market(
        self, market_id: HexAddress | None = None
    ) -> list[ContractPrediction]:
        where_stms = {}
        if market_id:
            where_stms["marketAddress"] = market_id.lower()

        prediction_added = (
            self.omen_agent_result_mapping_subgraph.Query.predictionAddeds(
                where=where_stms,
                orderBy="blockNumber",
                orderDirection="asc",
            )
        )
        fields = [
            prediction_added.publisherAddress,
            prediction_added.ipfsHash,
            prediction_added.txHashes,
            prediction_added.estimatedProbabilityBps,
        ]
        result = self.sg.query_json(fields)
        items = self._parse_items_from_json(result)
        if not items:
            return []
        return [ContractPrediction.model_validate(i) for i in items]
