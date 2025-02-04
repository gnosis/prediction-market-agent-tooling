from typing import Any

from subgrounds import FieldPath
from web3.constants import ADDRESS_ZERO

from prediction_market_agent_tooling.markets.base_subgraph_handler import (
    BaseSubgraphHandler,
)
from prediction_market_agent_tooling.markets.seer.data_models import (
    SeerMarket,
    SeerPool,
)
from prediction_market_agent_tooling.tools.hexbytes_custom import HexBytes

INVALID_OUTCOME = "Invalid result"


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
            markets_field.marketName,
            markets_field.parentOutcome,
            markets_field.outcomes,
            markets_field.parentMarket.id,
            markets_field.finalizeTs,
            markets_field.wrappedTokens,
        ]
        return fields

    @staticmethod
    def filter_bicategorical_markets(markets: list[SeerMarket]) -> list[SeerMarket]:
        # We do an extra check for the invalid outcome for safety.
        return [
            m for m in markets if len(m.outcomes) == 3 and INVALID_OUTCOME in m.outcomes
        ]

    @staticmethod
    def filter_binary_markets(markets: list[SeerMarket]) -> list[SeerMarket]:
        return [
            market
            for market in markets
            if {"yes", "no"}.issubset({o.lower() for o in market.outcomes})
        ]

    @staticmethod
    def build_filter_for_conditional_markets(
        include_conditional_markets: bool = True,
    ) -> dict[Any, Any]:
        return (
            {}
            if include_conditional_markets
            else {"parentMarket": ADDRESS_ZERO.lower()}
        )

    def get_bicategorical_markets(
        self, include_conditional_markets: bool = True
    ) -> list[SeerMarket]:
        """Returns markets that contain 2 categories plus an invalid outcome."""
        # Binary markets on Seer contain 3 outcomes: OutcomeA, outcomeB and an Invalid option.
        query_filter = self.build_filter_for_conditional_markets(
            include_conditional_markets
        )
        query_filter["outcomes_contains"] = [INVALID_OUTCOME]
        markets_field = self.seer_subgraph.Query.markets(where=query_filter)
        fields = self._get_fields_for_markets(markets_field)
        markets = self.do_query(fields=fields, pydantic_model=SeerMarket)
        two_category_markets = self.filter_bicategorical_markets(markets)
        return two_category_markets

    def get_binary_markets(
        self, include_conditional_markets: bool = True
    ) -> list[SeerMarket]:
        two_category_markets = self.get_bicategorical_markets(
            include_conditional_markets=include_conditional_markets
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
            pools_field.token0.id,
            pools_field.token0.name,
            pools_field.token0.symbol,
            pools_field.token1.id,
            pools_field.token1.name,
            pools_field.token1.symbol,
        ]
        return fields

    def get_swapr_pools_for_market(self, market: SeerMarket) -> list[SeerPool]:
        # We iterate through the wrapped tokens and put them in a where clause so that we hit the subgraph endpoint just once.
        wheres = []
        for wrapped_token in market.wrapped_tokens:
            wheres.extend(
                [
                    {"token0": wrapped_token.hex().lower()},
                    {"token1": wrapped_token.hex().lower()},
                ]
            )
        pools_field = self.swapr_algebra_subgraph.Query.pools(where={"or": wheres})
        fields = self._get_fields_for_pools(pools_field)
        pools = self.do_query(fields=fields, pydantic_model=SeerPool)
        return pools
