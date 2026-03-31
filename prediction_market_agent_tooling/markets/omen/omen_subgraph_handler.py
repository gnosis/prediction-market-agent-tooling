import sys
import typing as t

import requests
from PIL import Image
from PIL.Image import Image as ImageType

from prediction_market_agent_tooling.gtypes import (
    ChecksumAddress,
    HexAddress,
    HexBytes,
    Wei,
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
    OutcomeWei,
    RealityAnswer,
    RealityQuestion,
    RealityResponse,
)
from prediction_market_agent_tooling.markets.omen.omen_contracts import (
    EUReContract,
    GNOContract,
    OmenThumbnailMapping,
    WETHContract,
    WrappedxDaiContract,
    sDaiContract,
)
from prediction_market_agent_tooling.tools.caches.inmemory_cache import (
    persistent_inmemory_cache,
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

SAFE_COLLATERAL_TOKENS = [
    WrappedxDaiContract(),
    sDaiContract(),
    GNOContract(),
    WETHContract(),
    EUReContract(),
]
SAFE_COLLATERAL_TOKENS_ADDRESSES = [
    contract.address for contract in SAFE_COLLATERAL_TOKENS
]

# GraphQL field selections
OMEN_MARKET_QUESTION_FIELDS = (
    "id title outcomes answerFinalizedTimestamp currentAnswer "
    "data templateId isPendingArbitration openingTimestamp timeout"
)

OMEN_MARKET_FIELDS = (
    "id title creator collateralVolume usdVolume "
    "liquidityParameter collateralToken outcomes "
    "outcomeTokenAmounts outcomeTokenMarginalPrices "
    "lastActiveDay lastActiveHour fee "
    "answerFinalizedTimestamp resolutionTimestamp "
    "currentAnswer creationTimestamp category "
    f"condition {{ id outcomeSlotCount }} "
    f"question {{ {OMEN_MARKET_QUESTION_FIELDS} }}"
)

OMEN_BET_FIELDS = (
    "id title collateralToken outcomeTokenMarginalPrice "
    "oldOutcomeTokenMarginalPrice type "
    "creator { id } "
    "creationTimestamp collateralAmount feeAmount "
    "outcomeIndex outcomeTokensTraded transactionHash "
    f"fpmm {{ {OMEN_MARKET_FIELDS} }}"
)

REALITY_QUESTION_FIELDS = (
    "id user updatedTimestamp questionId contentHash "
    "historyHash answerFinalizedTimestamp "
    "currentScheduledFinalizationTimestamp"
)

REALITY_ANSWER_FIELDS = (
    "id answer bondAggregate lastBond timestamp createdBlock "
    f"question {{ {REALITY_QUESTION_FIELDS} }}"
)

REALITY_RESPONSE_FIELDS = (
    "id timestamp answer isUnrevealed isCommitment bond "
    "user historyHash createdBlock revealedBlock "
    f"question {{ {REALITY_QUESTION_FIELDS} }}"
)

POSITION_FIELDS = "id conditionIds collateralTokenAddress indexSets"

USER_POSITION_FIELDS = f"id balance wrappedBalance totalBalance position {{ {POSITION_FIELDS} }}"

IMAGE_MAPPING_FIELDS = "id image_hash"

PREDICTION_FIELDS = "publisherAddress ipfsHash txHashes estimatedProbabilityBps"


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

        api_key = self.keys.graph_api_key.get_secret_value()
        self.trades_subgraph_url = self.OMEN_TRADES_SUBGRAPH.format(
            graph_api_key=api_key
        )
        self.conditional_tokens_subgraph_url = (
            self.CONDITIONAL_TOKENS_SUBGRAPH.format(graph_api_key=api_key)
        )
        self.realityeth_subgraph_url = self.REALITYETH_GRAPH_URL.format(
            graph_api_key=api_key
        )
        self.omen_image_mapping_url = self.OMEN_IMAGE_MAPPING_GRAPH_URL.format(
            graph_api_key=api_key
        )
        self.omen_agent_result_mapping_url = (
            self.OMEN_AGENT_RESULT_MAPPING_GRAPH_URL.format(graph_api_key=api_key)
        )

    def _build_where_statements(
        self,
        creator: HexAddress | None,
        creator_in: t.Sequence[HexAddress] | None,
        created_after: DatetimeUTC | None,
        question_opened_before: DatetimeUTC | None,
        question_opened_after: DatetimeUTC | None,
        question_finalized_before: DatetimeUTC | None,
        question_finalized_after: DatetimeUTC | None,
        question_with_answers: bool | None,
        question_pending_arbitration: bool | None,
        question_id: HexBytes | None,
        question_id_in: list[HexBytes] | None,
        question_current_answer_before: DatetimeUTC | None,
        question_excluded_titles: set[str] | None,
        resolved: bool | None,
        liquidity_bigger_than: Wei | None,
        condition_id_in: list[HexBytes] | None,
        id_in: list[str] | None,
        collateral_token_address_in: t.Sequence[ChecksumAddress] | None,
        category: str | None,
        include_categorical_markets: bool = False,
        include_scalar_markets: bool = False,
    ) -> dict[str, t.Any]:
        where_stms: dict[str, t.Any] = {
            "title_not": None,
            "condition_": {},
        }
        if not include_categorical_markets:
            where_stms["outcomeSlotCount"] = 2
            where_stms["outcomes"] = OMEN_BINARY_MARKET_OUTCOMES

        if not include_scalar_markets:
            # scalar markets can be identified
            where_stms["outcomes_not"] = None

        where_stms["question_"] = self.get_omen_question_filters(
            question_id=question_id,
            opened_before=question_opened_before,
            opened_after=question_opened_after,
            finalized_before=question_finalized_before,
            finalized_after=question_finalized_after,
            with_answers=question_with_answers,
            pending_arbitration=question_pending_arbitration,
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
            where_stms["liquidityParameter_gt"] = liquidity_bigger_than.value

        if condition_id_in is not None:
            where_stms["condition_"]["id_in"] = [x.to_0x_hex() for x in condition_id_in]

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
    ) -> tuple[str | None, str | None]:
        match sort_by:
            case SortBy.NEWEST:
                return "desc", "creationTimestamp"
            case SortBy.CLOSING_SOONEST:
                return "asc", "openingTimestamp"
            case SortBy.HIGHEST_LIQUIDITY:
                return "desc", "liquidityMeasure"
            case SortBy.LOWEST_LIQUIDITY:
                return "asc", "liquidityMeasure"
            case SortBy.NONE:
                return None, None
            case _:
                raise ValueError(f"Unknown sort_by: {sort_by}")

    def get_omen_markets_simple(
        self,
        limit: t.Optional[int],
        # Enumerated values for simpler usage.
        filter_by: FilterBy,
        sort_by: SortBy,
        include_categorical_markets: bool = False,
        # Additional filters, these can not be modified by the enums above.
        created_after: DatetimeUTC | None = None,
        excluded_questions: set[str] | None = None,  # question titles
        collateral_token_address_in: (
            t.Sequence[ChecksumAddress] | None
        ) = SAFE_COLLATERAL_TOKENS_ADDRESSES,
        category: str | None = None,
        creator_in: t.Sequence[HexAddress] | None = None,
    ) -> t.List[OmenMarket]:
        """
        Simplified `get_omen_markets` method, which allows to fetch markets based on the filter_by and sort_by values.
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
            liquidity_bigger_than = Wei(0)
        elif filter_by == FilterBy.NONE:
            pass
        else:
            raise ValueError(f"Unknown filter_by: {filter_by}")

        sort_direction, sort_by_field = self._build_sort_params(sort_by)

        all_markets = self.get_omen_markets(
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
            include_categorical_markets=include_categorical_markets,
        )

        return all_markets

    def get_omen_markets(
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
        question_pending_arbitration: bool | None = None,
        question_id: HexBytes | None = None,
        question_id_in: list[HexBytes] | None = None,
        question_current_answer_before: DatetimeUTC | None = None,
        question_excluded_titles: set[str] | None = None,
        resolved: bool | None = None,
        liquidity_bigger_than: Wei | None = None,
        condition_id_in: list[HexBytes] | None = None,
        id_in: list[str] | None = None,
        sort_by_field: str | None = None,
        sort_direction: str | None = None,
        collateral_token_address_in: (
            t.Sequence[ChecksumAddress] | None
        ) = SAFE_COLLATERAL_TOKENS_ADDRESSES,
        category: str | None = None,
        include_categorical_markets: bool = True,
        include_scalar_markets: bool = False,
    ) -> t.List[OmenMarket]:
        """
        Complete method to fetch Omen  markets with various filters, use `get_omen_markets_simple` for simplified version that uses FilterBy and SortBy enums.
        """
        where_stms = self._build_where_statements(
            creator=creator,
            creator_in=creator_in,
            created_after=created_after,
            question_opened_before=question_opened_before,
            question_opened_after=question_opened_after,
            question_finalized_before=question_finalized_before,
            question_finalized_after=question_finalized_after,
            question_with_answers=question_with_answers,
            question_pending_arbitration=question_pending_arbitration,
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
            include_categorical_markets=include_categorical_markets,
            include_scalar_markets=include_scalar_markets,
        )

        return self.do_query(
            url=self.trades_subgraph_url,
            entity="fixedProductMarketMakers",
            fields=OMEN_MARKET_FIELDS,
            pydantic_model=OmenMarket,
            where=where_stms,
            first=limit if limit else sys.maxsize,
            order_by=sort_by_field,
            order_direction=sort_direction,
        )

    def get_omen_market_by_market_id(
        self, market_id: HexAddress, block_number: int | None = None
    ) -> OmenMarket:
        block = {"number": block_number} if block_number else None

        omen_markets = self.do_query(
            url=self.trades_subgraph_url,
            entity="fixedProductMarketMaker",
            fields=OMEN_MARKET_FIELDS,
            pydantic_model=OmenMarket,
            entity_id=market_id.lower(),
            block=block,
        )

        if len(omen_markets) != 1:
            raise ValueError(
                f"Fetched wrong number of markets. Expected 1 but got {len(omen_markets)}"
            )

        return omen_markets[0]

    def get_positions(
        self,
        condition_id: HexBytes | None = None,
    ) -> list[OmenPosition]:
        where_stms: dict[str, t.Any] = {}

        if condition_id is not None:
            where_stms["conditionIds_contains"] = [condition_id.to_0x_hex()]

        return self.do_query(
            url=self.conditional_tokens_subgraph_url,
            entity="positions",
            fields=POSITION_FIELDS,
            pydantic_model=OmenPosition,
            where=where_stms,
            first=sys.maxsize,
        )

    def get_user_positions(
        self,
        better_address: ChecksumAddress | None = None,
        user_position_id_in: list[HexBytes] | None = None,
        position_id_in: list[HexBytes] | None = None,
        total_balance_bigger_than: OutcomeWei | None = None,
    ) -> list[OmenUserPosition]:
        where_stms: dict[str, t.Any] = {
            "position_": {},
        }

        if better_address is not None:
            where_stms["user"] = better_address.lower()

        if total_balance_bigger_than is not None:
            where_stms["totalBalance_gt"] = total_balance_bigger_than.value

        if user_position_id_in is not None:
            where_stms["id_in"] = [x.to_0x_hex() for x in user_position_id_in]

        if position_id_in is not None:
            where_stms["position_"]["positionId_in"] = [
                x.to_0x_hex() for x in position_id_in
            ]

        return self.do_query(
            url=self.conditional_tokens_subgraph_url,
            entity="userPositions",
            fields=USER_POSITION_FIELDS,
            pydantic_model=OmenUserPosition,
            where=where_stms,
            first=sys.maxsize,
        )

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
        market_resolved_before: DatetimeUTC | None = None,
        market_resolved_after: DatetimeUTC | None = None,
        collateral_amount_more_than: Wei | None = None,
        sort_by_field: str | None = None,
        sort_direction: str | None = None,
    ) -> list[OmenBet]:
        if not end_time:
            end_time = utcnow()

        where_stms: dict[str, t.Any] = {}
        fpmm_filter: dict[str, t.Any] = {}

        if start_time:
            where_stms["creationTimestamp_gte"] = to_int_timestamp(start_time)
        if end_time:
            where_stms["creationTimestamp_lte"] = to_int_timestamp(end_time)
        if type_:
            where_stms["type"] = type_
        if better_address:
            where_stms["creator"] = better_address.lower()
        if market_id:
            where_stms["fpmm"] = market_id.lower()
        if filter_by_answer_finalized_not_null:
            fpmm_filter["answerFinalizedTimestamp_not"] = None
        if market_opening_after is not None:
            fpmm_filter["openingTimestamp_gt"] = to_int_timestamp(
                market_opening_after
            )
        if market_resolved_after is not None:
            fpmm_filter["resolutionTimestamp_gt"] = to_int_timestamp(
                market_resolved_after
            )
        if market_resolved_before is not None:
            fpmm_filter["resolutionTimestamp_lt"] = to_int_timestamp(
                market_resolved_before
            )
        if collateral_amount_more_than is not None:
            where_stms["collateralAmount_gt"] = collateral_amount_more_than.value

        if fpmm_filter:
            where_stms["fpmm_"] = fpmm_filter

        return self.do_query(
            url=self.trades_subgraph_url,
            entity="fpmmTrades",
            fields=OMEN_BET_FIELDS,
            pydantic_model=OmenBet,
            where=where_stms,
            first=limit if limit else sys.maxsize,
            order_by=sort_by_field,
            order_direction=sort_direction,
        )

    def get_bets(
        self,
        better_address: ChecksumAddress | None = None,
        start_time: DatetimeUTC | None = None,
        end_time: t.Optional[DatetimeUTC] = None,
        market_id: t.Optional[ChecksumAddress] = None,
        filter_by_answer_finalized_not_null: bool = False,
        market_opening_after: DatetimeUTC | None = None,
        market_resolved_before: DatetimeUTC | None = None,
        market_resolved_after: DatetimeUTC | None = None,
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
            market_resolved_before=market_resolved_before,
            market_resolved_after=market_resolved_after,
            collateral_amount_more_than=collateral_amount_more_than,
        )

    def get_resolved_bets(
        self,
        better_address: ChecksumAddress,
        start_time: DatetimeUTC | None = None,
        end_time: t.Optional[DatetimeUTC] = None,
        market_id: t.Optional[ChecksumAddress] = None,
        market_resolved_before: DatetimeUTC | None = None,
        market_resolved_after: DatetimeUTC | None = None,
    ) -> list[OmenBet]:
        omen_bets = self.get_bets(
            better_address=better_address,
            start_time=start_time,
            end_time=end_time,
            market_id=market_id,
            filter_by_answer_finalized_not_null=True,
            market_resolved_before=market_resolved_before,
            market_resolved_after=market_resolved_after,
        )
        return [b for b in omen_bets if b.fpmm.is_resolved]

    def get_resolved_bets_with_valid_answer(
        self,
        better_address: ChecksumAddress,
        start_time: DatetimeUTC | None = None,
        end_time: t.Optional[DatetimeUTC] = None,
        market_resolved_before: DatetimeUTC | None = None,
        market_resolved_after: DatetimeUTC | None = None,
        market_id: t.Optional[ChecksumAddress] = None,
    ) -> list[OmenBet]:
        bets = self.get_resolved_bets(
            better_address=better_address,
            start_time=start_time,
            end_time=end_time,
            market_id=market_id,
            market_resolved_before=market_resolved_before,
            market_resolved_after=market_resolved_after,
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
        pending_arbitration: bool | None,
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
            where_stms["questionId"] = question_id.to_0x_hex()

        if claimed is not None:
            if claimed:
                where_stms["historyHash"] = ZERO_BYTES.to_0x_hex()
            else:
                where_stms["historyHash_not"] = ZERO_BYTES.to_0x_hex()

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
                where_stms["currentAnswer_not"] = None
            else:
                where_stms["currentAnswer"] = None

        if pending_arbitration is not None:
            where_stms["isPendingArbitration"] = pending_arbitration

        if question_id_in is not None:
            # Be aware: On Omen subgraph, question's `id` represents `questionId` on reality subgraph. And `id` on reality subraph is just a weird concat of multiple things from the question.
            where_stms["questionId_in"] = [x.to_0x_hex() for x in question_id_in]

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
        pending_arbitration: bool | None,
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
            where_stms["id"] = question_id.to_0x_hex()

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
                where_stms["currentAnswer_not"] = None
            else:
                where_stms["currentAnswer"] = None

        if pending_arbitration is not None:
            where_stms["isPendingArbitration"] = pending_arbitration

        if question_id_in is not None:
            # Be aware: On Omen subgraph, question's `id` represents `questionId` on reality subgraph. And `id` on reality subraph is just a weird concat of multiple things from the question.
            where_stms["id_in"] = [x.to_0x_hex() for x in question_id_in]

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
        pending_arbitration: bool | None = None,
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
            pending_arbitration=pending_arbitration,
            current_answer_before=current_answer_before,
            question_id_in=question_id_in,
            question_id=question_id,
            opened_before=opened_before,
            opened_after=opened_after,
            excluded_titles=excluded_titles,
        )

        return self.do_query(
            url=self.realityeth_subgraph_url,
            entity="questions",
            fields=REALITY_QUESTION_FIELDS,
            pydantic_model=RealityQuestion,
            where=where_stms,
            first=limit if limit else sys.maxsize,
        )

    def get_answers(self, question_id: HexBytes) -> list[RealityAnswer]:
        where_stms: dict[str, t.Any] = {
            "question_": {"questionId": question_id.to_0x_hex()},
        }

        return self.do_query(
            url=self.realityeth_subgraph_url,
            entity="answers",
            fields=REALITY_ANSWER_FIELDS,
            pydantic_model=RealityAnswer,
            where=where_stms,
        )

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
        question_pending_arbitration: bool | None = None,
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
            pending_arbitration=question_pending_arbitration,
            current_answer_before=question_current_answer_before,
            question_id_in=question_id_in,
            excluded_titles=question_excluded_titles,
        )

        return self.do_query(
            url=self.realityeth_subgraph_url,
            entity="responses",
            fields=REALITY_RESPONSE_FIELDS,
            pydantic_model=RealityResponse,
            where=where_stms,
            first=limit if limit else sys.maxsize,
        )

    def get_markets_from_all_user_positions(
        self, user_positions: list[OmenUserPosition]
    ) -> list[OmenMarket]:
        unique_condition_ids: list[HexBytes] = list(
            set(sum([u.position.conditionIds for u in user_positions], []))
        )
        markets = self.get_omen_markets(
            limit=sys.maxsize, condition_id_in=unique_condition_ids
        )
        return markets

    def get_market_from_user_position(
        self, user_position: OmenUserPosition
    ) -> OmenMarket:
        """Markets and user positions are uniquely connected via condition_ids"""
        condition_ids = user_position.position.conditionIds
        markets = self.get_omen_markets(limit=1, condition_id_in=condition_ids)
        if len(markets) != 1:
            raise ValueError(
                f"Incorrect number of markets fetched {len(markets)}, expected 1."
            )
        return markets[0]

    def get_market_image_url(self, market_id: HexAddress) -> str | None:
        items = self.query_subgraph(
            url=self.omen_image_mapping_url,
            entity="omenThumbnailMapping",
            fields=IMAGE_MAPPING_FIELDS,
            entity_id=market_id.lower(),
        )
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
        where_stms: dict[str, t.Any] = {}
        if market_id:
            where_stms["marketAddress"] = market_id.lower()

        items = self.query_subgraph(
            url=self.omen_agent_result_mapping_url,
            entity="predictionAddeds",
            fields=PREDICTION_FIELDS,
            where=where_stms,
            order_by="blockNumber",
            order_direction="asc",
        )
        if not items:
            return []
        return [ContractPrediction.model_validate(i) for i in items]

    def get_agent_results_for_bet(self, bet: OmenBet) -> ContractPrediction | None:
        results = [
            result
            for result in self.get_agent_results_for_market(bet.fpmm.id)
            if bet.transactionHash in result.tx_hashes
        ]

        if not results:
            return None
        elif len(results) > 1:
            raise RuntimeError("Multiple results found for a single bet.")

        return results[0]


@persistent_inmemory_cache
def get_omen_market_by_market_id_cached(
    market_id: HexAddress,
    block_number: int,  # Force `block_number` to be provided, because `latest` block constantly updates.
) -> OmenMarket:
    return OmenSubgraphHandler().get_omen_market_by_market_id(
        market_id, block_number=block_number
    )
