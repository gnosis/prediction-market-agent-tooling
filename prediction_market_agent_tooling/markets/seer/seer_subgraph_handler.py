import sys
import typing as t
from collections import defaultdict
from enum import Enum
from typing import Any

from subgrounds import FieldPath
from web3.constants import ADDRESS_ZERO

from prediction_market_agent_tooling.deploy.constants import (
    DOWN_OUTCOME_LOWERCASE_IDENTIFIER,
    NO_OUTCOME_LOWERCASE_IDENTIFIER,
    UP_OUTCOME_LOWERCASE_IDENTIFIER,
    YES_OUTCOME_LOWERCASE_IDENTIFIER,
)
from prediction_market_agent_tooling.gtypes import ChecksumAddress, Wei
from prediction_market_agent_tooling.loggers import logger
from prediction_market_agent_tooling.markets.agent_market import (
    ConditionalFilterType,
    FilterBy,
    QuestionType,
    SortBy,
)
from prediction_market_agent_tooling.markets.base_subgraph_handler import (
    BaseSubgraphHandler,
)
from prediction_market_agent_tooling.markets.seer.data_models import (
    SeerMarket,
    SeerMarketQuestions,
    SeerMarketWithQuestions,
)
from prediction_market_agent_tooling.markets.seer.subgraph_data_models import SeerPool
from prediction_market_agent_tooling.tools.hexbytes_custom import HexBytes
from prediction_market_agent_tooling.tools.singleton import SingletonMeta
from prediction_market_agent_tooling.tools.utils import to_int_timestamp, utcnow
from prediction_market_agent_tooling.tools.web3_utils import unwrap_generic_value


class TemplateId(int, Enum):
    """Template IDs used in Reality.eth questions."""

    SCALAR = 1
    CATEGORICAL = 2
    MULTICATEGORICAL = 3


class SeerSubgraphHandler(BaseSubgraphHandler):
    """
    Class responsible for handling interactions with Seer subgraphs.
    """

    SEER_SUBGRAPH = "https://gateway-arbitrum.network.thegraph.com/api/{graph_api_key}/subgraphs/id/B4vyRqJaSHD8dRDb3BFRoAzuBK18c1QQcXq94JbxDxWH"

    SWAPR_ALGEBRA_SUBGRAPH = "https://gateway-arbitrum.network.thegraph.com/api/{graph_api_key}/subgraphs/id/AAA1vYjxwFHzbt6qKwLHNcDSASyr1J1xVViDH8gTMFMR"

    INVALID_ANSWER = "ffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffff"

    def __init__(self) -> None:
        super().__init__()

        self.seer_subgraph = self.sg.load_subgraph(
            self.SEER_SUBGRAPH.format(
                graph_api_key=self.keys.graph_api_key.get_secret_value()
            )
        )
        self.swapr_algebra_subgraph = self.sg.load_subgraph(
            self.SWAPR_ALGEBRA_SUBGRAPH.format(
                graph_api_key=self.keys.graph_api_key.get_secret_value()
            )
        )

    def _get_fields_for_markets(
        self, markets_field: FieldPath, current_level: int = 0, max_level: int = 1
    ) -> list[FieldPath]:
        fields = [
            markets_field.id,
            markets_field.factory,
            markets_field.creator,
            markets_field.conditionId,
            markets_field.marketName,
            markets_field.outcomesSupply,
            markets_field.parentOutcome,
            markets_field.outcomes,
            markets_field.payoutReported,
            markets_field.payoutNumerators,
            markets_field.hasAnswers,
            markets_field.blockTimestamp,
            markets_field.openingTs,
            markets_field.finalizeTs,
            markets_field.wrappedTokens,
            markets_field.collateralToken,
            markets_field.upperBound,
            markets_field.lowerBound,
            markets_field.templateId,
        ]
        if current_level < max_level:
            fields.extend(
                self._get_fields_for_markets(
                    markets_field.parentMarket, current_level + 1, max_level
                )
            )
            # TODO: Same situation as with `questions` field above.
            # fields.extend(
            #     self._get_fields_for_markets(
            #         markets_field.childMarkets, current_level + 1, max_level
            #     )
            # )
        return fields

    @staticmethod
    def filter_bicategorical_markets(markets: list[SeerMarket]) -> list[SeerMarket]:
        # We do an extra check for the invalid outcome for safety.
        return [m for m in markets if len(m.outcomes) == 3]

    @staticmethod
    def _create_case_variations_condition(
        identifier: str,
        outcome_condition: str = "outcomes_contains",
        condition: str = "or",
    ) -> dict[str, list[dict[str, list[str]]]]:
        return {
            condition: [
                {outcome_condition: [variation]}
                for variation in [
                    identifier.lower(),
                    identifier.capitalize(),
                    identifier.upper(),
                ]
            ]
        }

    @staticmethod
    def _build_where_statements(
        filter_by: FilterBy,
        outcome_supply_gt_if_open: Wei,
        question_type: QuestionType = QuestionType.ALL,
        conditional_filter_type: ConditionalFilterType = ConditionalFilterType.ONLY_NOT_CONDITIONAL,
        parent_market_id: HexBytes | None = None,
    ) -> dict[Any, Any]:
        now = to_int_timestamp(utcnow())

        and_stms: dict[str, t.Any] = {}

        match filter_by:
            case FilterBy.OPEN:
                and_stms["openingTs_gt"] = now
                and_stms["hasAnswers"] = False
                and_stms["outcomesSupply_gt"] = outcome_supply_gt_if_open.value
            case FilterBy.RESOLVED:
                # We consider RESOLVED == CLOSED (on Seer UI)
                and_stms["payoutReported"] = True
            case FilterBy.NONE:
                pass
            case _:
                raise ValueError(f"Unknown filter {filter_by}")

        if parent_market_id:
            and_stms["parentMarket"] = parent_market_id.to_0x_hex().lower()

        outcome_filters: list[dict[str, t.Any]] = []

        if question_type == QuestionType.SCALAR:
            # Template ID "1" + UP/DOWN outcomes for scalar markets
            and_stms["templateId"] = TemplateId.SCALAR.value
            up_filter = SeerSubgraphHandler._create_case_variations_condition(
                UP_OUTCOME_LOWERCASE_IDENTIFIER, "outcomes_contains", "or"
            )
            down_filter = SeerSubgraphHandler._create_case_variations_condition(
                DOWN_OUTCOME_LOWERCASE_IDENTIFIER, "outcomes_contains", "or"
            )
            outcome_filters.extend([up_filter, down_filter])

        elif question_type == QuestionType.BINARY:
            # Template ID "2" + YES/NO outcomes for binary markets
            and_stms["templateId"] = TemplateId.CATEGORICAL.value
            yes_filter = SeerSubgraphHandler._create_case_variations_condition(
                YES_OUTCOME_LOWERCASE_IDENTIFIER, "outcomes_contains", "or"
            )
            no_filter = SeerSubgraphHandler._create_case_variations_condition(
                NO_OUTCOME_LOWERCASE_IDENTIFIER, "outcomes_contains", "or"
            )
            outcome_filters.extend([yes_filter, no_filter])

        elif question_type == QuestionType.CATEGORICAL:
            # Template ID 2 (categorical) OR Template ID 3 (multi-categorical,
            # we treat them as categorical for now for simplicity)
            # https://reality.eth.limo/app/docs/html/contracts.html#templates
            outcome_filters.append(
                {
                    "or": [
                        {"templateId": TemplateId.CATEGORICAL.value},
                        {"templateId": TemplateId.MULTICATEGORICAL.value},
                    ]
                }
            )

        # Build filters for conditional_filter type
        conditional_filter = {}
        match conditional_filter_type:
            case ConditionalFilterType.ONLY_CONDITIONAL:
                conditional_filter["parentMarket_not"] = ADDRESS_ZERO.lower()
            case ConditionalFilterType.ONLY_NOT_CONDITIONAL:
                conditional_filter["parentMarket"] = ADDRESS_ZERO.lower()
            case ConditionalFilterType.ALL:
                pass
            case _:
                raise ValueError(
                    f"Unknown conditional filter {conditional_filter_type}"
                )

        all_filters = outcome_filters + [and_stms, conditional_filter]
        where_stms: dict[str, t.Any] = {"and": all_filters}
        return where_stms

    def _build_sort_params(
        self, sort_by: SortBy
    ) -> tuple[str | None, FieldPath | None]:
        sort_direction: str | None
        sort_by_field: FieldPath | None

        match sort_by:
            case SortBy.NEWEST:
                sort_direction = "desc"
                sort_by_field = self.seer_subgraph.Market.blockTimestamp
            case SortBy.CLOSING_SOONEST:
                sort_direction = "asc"
                sort_by_field = self.seer_subgraph.Market.openingTs
            case SortBy.HIGHEST_LIQUIDITY | SortBy.LOWEST_LIQUIDITY:
                sort_direction = (
                    "desc" if sort_by == SortBy.HIGHEST_LIQUIDITY else "asc"
                )
                sort_by_field = self.seer_subgraph.Market.outcomesSupply
            case SortBy.NONE:
                sort_direction = None
                sort_by_field = None
            case _:
                raise ValueError(f"Unknown sort_by: {sort_by}")

        return sort_direction, sort_by_field

    def get_markets(
        self,
        filter_by: FilterBy,
        sort_by: SortBy = SortBy.NONE,
        limit: int | None = None,
        outcome_supply_gt_if_open: Wei = Wei(0),
        question_type: QuestionType = QuestionType.ALL,
        conditional_filter_type: ConditionalFilterType = ConditionalFilterType.ONLY_NOT_CONDITIONAL,
        parent_market_id: HexBytes | None = None,
    ) -> list[SeerMarketWithQuestions]:
        sort_direction, sort_by_field = self._build_sort_params(sort_by)

        where_stms = self._build_where_statements(
            filter_by=filter_by,
            outcome_supply_gt_if_open=outcome_supply_gt_if_open,
            parent_market_id=parent_market_id,
            question_type=question_type,
            conditional_filter_type=conditional_filter_type,
        )

        # These values can not be set to `None`, but they can be omitted.
        optional_params = {}
        if sort_by_field is not None:
            optional_params["orderBy"] = sort_by_field
        if sort_direction is not None:
            optional_params["orderDirection"] = sort_direction

        markets_field = self.seer_subgraph.Query.markets(
            first=(
                limit if limit else sys.maxsize
            ),  # if not limit, we fetch all possible markets,
            where=unwrap_generic_value(where_stms),
            **optional_params,
        )
        fields = self._get_fields_for_markets(markets_field)
        markets = self.do_query(fields=fields, pydantic_model=SeerMarket)
        market_ids = [m.id for m in markets]
        # We fetch questions from all markets and all parents in one go
        parent_market_ids = [
            m.parent_market.id for m in markets if m.parent_market is not None
        ]
        q = SeerQuestionsCache(seer_subgraph_handler=self)
        q.fetch_questions(list(set(market_ids + parent_market_ids)))

        # Create SeerMarketWithQuestions for each market
        return [
            SeerMarketWithQuestions(
                **m.model_dump(), questions=q.market_id_to_questions[m.id]
            )
            for m in markets
        ]

    def get_questions_for_markets(
        self, market_ids: list[HexBytes]
    ) -> list[SeerMarketQuestions]:
        where = unwrap_generic_value(
            {"market_in": [market_id.to_0x_hex().lower() for market_id in market_ids]}
        )
        markets_field = self.seer_subgraph.Query.marketQuestions(where=where)
        fields = self._get_fields_for_questions(markets_field)
        questions = self.do_query(fields=fields, pydantic_model=SeerMarketQuestions)
        return questions

    def get_market_by_id(self, market_id: HexBytes) -> SeerMarketWithQuestions:
        markets_field = self.seer_subgraph.Query.market(
            id=market_id.to_0x_hex().lower()
        )
        fields = self._get_fields_for_markets(markets_field)
        markets = self.do_query(fields=fields, pydantic_model=SeerMarket)
        if len(markets) != 1:
            raise ValueError(
                f"Fetched wrong number of markets. Expected 1 but got {len(markets)}"
            )
        q = SeerQuestionsCache(self)
        q.fetch_questions([market_id])
        questions = q.market_id_to_questions[market_id]
        s = SeerMarketWithQuestions.model_validate(
            markets[0].model_dump() | {"questions": questions}
        )
        return s

    def _get_fields_for_questions(self, questions_field: FieldPath) -> list[FieldPath]:
        fields = [
            questions_field.question.id,
            questions_field.question.best_answer,
            questions_field.question.finalize_ts,
            questions_field.market.id,
        ]
        return fields

    def get_market_by_wrapped_token(self, token: ChecksumAddress) -> SeerMarket:
        where_stms = {"wrappedTokens_contains": [token]}
        markets_field = self.seer_subgraph.Query.markets(
            where=unwrap_generic_value(where_stms)
        )
        fields = self._get_fields_for_markets(markets_field)
        markets = self.do_query(fields=fields, pydantic_model=SeerMarket)
        if len(markets) != 1:
            raise ValueError(
                f"Fetched wrong number of markets. Expected 1 but got {len(markets)}"
            )
        return markets[0]

    def _get_fields_for_pools(self, pools_field: FieldPath) -> list[FieldPath]:
        fields = [
            pools_field.id,
            pools_field.liquidity,
            pools_field.sqrtPrice,
            pools_field.token0Price,
            pools_field.token1Price,
            pools_field.token0.id,
            pools_field.token0.name,
            pools_field.token0.symbol,
            pools_field.token1.id,
            pools_field.token1.name,
            pools_field.token1.symbol,
            pools_field.totalValueLockedToken0,
            pools_field.totalValueLockedToken1,
        ]
        return fields

    def get_pool_by_token(
        self, token_address: ChecksumAddress, collateral_address: ChecksumAddress
    ) -> SeerPool | None:
        # We iterate through the wrapped tokens and put them in a where clause so that we hit the subgraph endpoint just once.

        where_argument = {
            "or": [
                {
                    "token0_": {"id": token_address.lower()},
                    "token1_": {"id": collateral_address.lower()},
                },
                {
                    "token0_": {"id": collateral_address.lower()},
                    "token1_": {"id": token_address.lower()},
                },
            ]
        }
        optional_params = {}
        optional_params["orderBy"] = self.swapr_algebra_subgraph.Pool.liquidity
        optional_params["orderDirection"] = "desc"

        pools_field = self.swapr_algebra_subgraph.Query.pools(
            where=unwrap_generic_value(where_argument), **optional_params
        )

        fields = self._get_fields_for_pools(pools_field)
        pools = self.do_query(fields=fields, pydantic_model=SeerPool)
        # We assume there is only one pool for outcomeToken/sDAI.
        if len(pools) > 1:
            logger.info(
                f"Multiple pools found for token {token_address}, selecting the first."
            )
        if pools:
            # We select the first one
            return pools[0]
        return None


class SeerQuestionsCache(metaclass=SingletonMeta):
    """A singleton cache for storing and retrieving Seer market questions.

    This class provides an in-memory cache for Seer market questions, preventing
    redundant subgraph queries by maintaining a mapping of market IDs to their
    associated questions. It implements the singleton pattern to ensure a single
    cache instance is used throughout the agent run.

    Attributes:
        market_id_to_questions: A dictionary mapping market IDs to lists of SeerMarketQuestions
        seer_subgraph_handler: Handler for interacting with the Seer subgraph
    """

    def __init__(self, seer_subgraph_handler: SeerSubgraphHandler | None = None):
        self.market_id_to_questions: dict[
            HexBytes, list[SeerMarketQuestions]
        ] = defaultdict(list)
        self.seer_subgraph_handler = seer_subgraph_handler or SeerSubgraphHandler()

    def fetch_questions(self, market_ids: list[HexBytes]) -> None:
        filtered_list = [
            market_id
            for market_id in market_ids
            if market_id not in self.market_id_to_questions
        ]
        if not filtered_list:
            return

        questions = self.seer_subgraph_handler.get_questions_for_markets(filtered_list)
        # Group questions by market_id
        questions_by_market: dict[HexBytes, list[SeerMarketQuestions]] = defaultdict(
            list
        )
        for q in questions:
            questions_by_market[q.market.id].append(q)

        # Update the cache with the new questions for each market
        for market_id, market_questions in questions_by_market.items():
            self.market_id_to_questions[market_id] = market_questions
