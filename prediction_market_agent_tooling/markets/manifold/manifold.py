import typing as t
from datetime import timedelta

from prediction_market_agent_tooling.config import APIKeys
from prediction_market_agent_tooling.gtypes import (
    USD,
    CollateralToken,
    OutcomeStr,
    Probability,
)
from prediction_market_agent_tooling.markets.agent_market import (
    AgentMarket,
    FilterBy,
    MarketFees,
    SortBy,
)
from prediction_market_agent_tooling.markets.manifold.api import (
    get_authenticated_user,
    get_manifold_bets,
    get_manifold_binary_markets,
    get_manifold_market,
    place_bet,
)
from prediction_market_agent_tooling.markets.manifold.data_models import (
    MANIFOLD_BASE_URL,
    FullManifoldMarket,
    usd_to_mana,
)
from prediction_market_agent_tooling.tools.utils import DatetimeUTC, utcnow


class ManifoldAgentMarket(AgentMarket):
    """
    Manifold's market class that can be used by agents to make predictions.
    """

    base_url: t.ClassVar[str] = MANIFOLD_BASE_URL

    # Manifold has additional fees than `platform_absolute`, but they don't expose them in the API before placing the bet, see https://docs.manifold.markets/api.
    # So we just consider them as 0, which anyway is true for all markets I randomly checked on Manifold.
    fees: MarketFees = MarketFees(
        bet_proportion=0,
        absolute=0.25,  # For doing trades via API.
    )

    # We restrict Manifold to binary markets, hence current_p_yes always defined.
    current_p_yes: Probability

    def get_last_trade_p_yes(self) -> Probability:
        """On Manifold, probablities aren't updated after the closure, so we can just use the current probability"""
        return self.current_p_yes

    def get_tiny_bet_amount(self) -> CollateralToken:
        return CollateralToken(1)

    def have_bet_on_market_since(self, keys: APIKeys, since: timedelta) -> bool:
        start_time = utcnow() - since
        recently_betted_questions = set(
            get_manifold_market(b.contractId).question
            for b in get_manifold_bets(
                user_id=get_authenticated_user(
                    keys.manifold_api_key.get_secret_value()
                ).id,
                start_time=start_time,
                end_time=None,
            )
        )
        return self.question in recently_betted_questions

    def place_bet(self, outcome: OutcomeStr, amount: USD) -> str:
        self.get_usd_in_token(amount)
        bet = place_bet(
            amount=usd_to_mana(amount),
            market_id=self.id,
            outcome=outcome,
            manifold_api_key=APIKeys().manifold_api_key,
        )
        return bet.id

    @staticmethod
    def from_data_model(model: FullManifoldMarket) -> "ManifoldAgentMarket":
        outcome_token_pool = {o: model.pool.size_for_outcome(o) for o in model.outcomes}

        prob_map = AgentMarket.build_probability_map(
            outcomes=list(outcome_token_pool.keys()),
            outcome_token_amounts=list(
                [i.as_outcome_wei for i in outcome_token_pool.values()]
            ),
        )

        return ManifoldAgentMarket(
            id=model.id,
            question=model.question,
            description=model.textDescription,
            outcomes=model.outcomes,
            resolution=model.resolution,
            created_time=model.createdTime,
            close_time=model.closeTime,
            current_p_yes=model.probability,
            url=model.url,
            volume=model.volume,
            outcome_token_pool=outcome_token_pool,
            probabilities=prob_map,
        )

    @staticmethod
    def get_markets(
        limit: int,
        sort_by: SortBy,
        filter_by: FilterBy = FilterBy.OPEN,
        created_after: t.Optional[DatetimeUTC] = None,
        excluded_questions: set[str] | None = None,
        fetch_categorical_markets: bool = False,
        fetch_scalar_markets: bool = False,
        fetch_conditional_markets: bool = False,
    ) -> t.Sequence["ManifoldAgentMarket"]:
        sort: t.Literal["newest", "close-date"] | None
        if sort_by == SortBy.CLOSING_SOONEST:
            sort = "close-date"
        elif sort_by == SortBy.NEWEST:
            sort = "newest"
        elif sort_by == SortBy.NONE:
            sort = None
        else:
            raise ValueError(f"Unknown sort_by: {sort_by}")

        filter_: t.Literal["open", "resolved"] | None
        if filter_by == FilterBy.OPEN:
            filter_ = "open"
        elif filter_by == FilterBy.RESOLVED:
            filter_ = "resolved"
        elif filter_by == FilterBy.NONE:
            filter_ = None
        else:
            raise ValueError(f"Unknown filter_by: {filter_by}")

        return [
            ManifoldAgentMarket.from_data_model(get_manifold_market(m.id))
            for m in get_manifold_binary_markets(
                limit=limit,
                sort=sort,
                created_after=created_after,
                filter_=filter_,
                excluded_questions=excluded_questions,
            )
        ]

    @staticmethod
    def redeem_winnings(api_keys: APIKeys) -> None:
        # It's done automatically on Manifold.
        pass

    @classmethod
    def get_user_url(cls, keys: APIKeys) -> str:
        return get_authenticated_user(keys.manifold_api_key.get_secret_value()).url

    @staticmethod
    def get_user_id(api_keys: APIKeys) -> str:
        return api_keys.manifold_user_id
