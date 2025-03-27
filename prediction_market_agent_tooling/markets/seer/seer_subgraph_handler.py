import sys
import typing as t
from typing import Any

from subgrounds import FieldPath
from web3.constants import ADDRESS_ZERO

from prediction_market_agent_tooling.gtypes import ChecksumAddress
from prediction_market_agent_tooling.loggers import logger
from prediction_market_agent_tooling.markets.agent_market import FilterBy, SortBy
from prediction_market_agent_tooling.markets.base_subgraph_handler import (
    BaseSubgraphHandler,
)
from prediction_market_agent_tooling.markets.omen.omen_constants import (
    SDAI_CONTRACT_ADDRESS,
)
from prediction_market_agent_tooling.markets.seer.data_models import SeerMarket
from prediction_market_agent_tooling.markets.seer.subgraph_data_models import SeerPool
from prediction_market_agent_tooling.tools.hexbytes_custom import HexBytes
from prediction_market_agent_tooling.tools.utils import to_int_timestamp, utcnow


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

    def _get_fields_for_markets(self, markets_field: FieldPath) -> list[FieldPath]:
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
            markets_field.parentMarket.id,
            markets_field.openingTs,
            markets_field.finalizeTs,
            markets_field.wrappedTokens,
            markets_field.collateralToken,
        ]
        return fields

    @staticmethod
    def filter_bicategorical_markets(markets: list[SeerMarket]) -> list[SeerMarket]:
        # We do an extra check for the invalid outcome for safety.
        return [m for m in markets if len(m.outcomes) == 3]

    @staticmethod
    def filter_binary_markets(markets: list[SeerMarket]) -> list[SeerMarket]:
        return [
            market
            for market in markets
            if {"yes", "no"}.issubset({o.lower() for o in market.outcomes})
        ]

    @staticmethod
    def _build_where_statements(
        filter_by: FilterBy,
        include_conditional_markets: bool = False,
    ) -> dict[Any, Any]:
        now = to_int_timestamp(utcnow())

        and_stms: dict[str, t.Any] = {}

        match filter_by:
            case FilterBy.OPEN:
                and_stms["openingTs_gt"] = now
                and_stms["hasAnswers"] = False
            case FilterBy.RESOLVED:
                # We consider RESOLVED == CLOSED (on Seer UI)
                and_stms["payoutReported"] = True
            case FilterBy.NONE:
                pass
            case _:
                raise ValueError(f"Unknown filter {filter_by}")

        if not include_conditional_markets:
            and_stms["parentMarket"] = ADDRESS_ZERO.lower()

        # We are only interested in binary markets of type YES/NO/Invalid.
        or_stms = {}
        or_stms["or"] = [
            {"outcomes_contains": ["YES"]},
            {"outcomes_contains": ["Yes"]},
            {"outcomes_contains": ["yes"]},
        ]

        where_stms: dict[str, t.Any] = {"and": [and_stms, or_stms]}
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

    def get_bicategorical_markets(
        self,
        filter_by: FilterBy,
        limit: int | None = None,
        sort_by_field: FieldPath | None = None,
        sort_direction: str | None = None,
        include_conditional_markets: bool = True,
    ) -> list[SeerMarket]:
        """Returns markets that contain 2 categories plus an invalid outcome."""
        # Binary markets on Seer contain 3 outcomes: OutcomeA, outcomeB and an Invalid option.
        where_stms = self._build_where_statements(
            filter_by=filter_by, include_conditional_markets=include_conditional_markets
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
            where=where_stms,
            **optional_params,
        )
        fields = self._get_fields_for_markets(markets_field)
        markets = self.do_query(fields=fields, pydantic_model=SeerMarket)
        two_category_markets = self.filter_bicategorical_markets(markets)
        return two_category_markets

    def get_binary_markets(
        self,
        filter_by: FilterBy,
        sort_by: SortBy = SortBy.NONE,
        limit: int | None = None,
        include_conditional_markets: bool = True,
    ) -> list[SeerMarket]:
        sort_direction, sort_by_field = self._build_sort_params(sort_by)

        two_category_markets = self.get_bicategorical_markets(
            limit=limit,
            include_conditional_markets=include_conditional_markets,
            sort_direction=sort_direction,
            sort_by_field=sort_by_field,
            filter_by=filter_by,
        )
        # Now we additionally filter markets based on YES/NO being the only outcomes.
        binary_markets = self.filter_binary_markets(two_category_markets)
        return binary_markets

    def get_market_by_id(self, market_id: HexBytes) -> SeerMarket:
        markets_field = self.seer_subgraph.Query.market(id=market_id.hex().lower())
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
        ]
        return fields

    def get_pool_by_token(self, token_address: ChecksumAddress) -> SeerPool | None:
        # We iterate through the wrapped tokens and put them in a where clause so that we hit the subgraph endpoint just once.
        wheres = []
        wheres.extend(
            [
                {
                    "token0": token_address.lower(),
                    "token1": SDAI_CONTRACT_ADDRESS.lower(),
                },
                {
                    "token0": SDAI_CONTRACT_ADDRESS.lower(),
                    "token1": token_address.lower(),
                },
            ]
        )

        optional_params = {}
        optional_params["orderBy"] = self.swapr_algebra_subgraph.Pool.liquidity
        optional_params["orderDirection"] = "desc"

        pools_field = self.swapr_algebra_subgraph.Query.pools(
            where={"or": wheres}, **optional_params
        )
        fields = self._get_fields_for_pools(pools_field)
        pools = self.do_query(fields=fields, pydantic_model=SeerPool)
        # We assume there is only one pool for outcomeToken/sDAI.
        if len(pools) > 1:
            logger.warning(
                f"Multiple pools found for token {token_address}, selecting the first."
            )
        if pools:
            # We select the first one
            return pools[0]
        return None
