import typing as t

from pydantic import field_validator
from pydantic_core.core_schema import FieldValidationInfo

from prediction_market_agent_tooling.config import APIKeys
from prediction_market_agent_tooling.gtypes import OutcomeStr, Probability
from prediction_market_agent_tooling.markets.agent_market import (
    AgentMarket,
    FilterBy,
    MarketFees,
    MarketType,
    ProcessedMarket,
    SortBy,
)
from prediction_market_agent_tooling.markets.metaculus.api import (
    METACULUS_API_BASE_URL,
    get_questions,
    make_prediction,
    post_question_comment,
)
from prediction_market_agent_tooling.markets.metaculus.data_models import (
    MetaculusQuestion,
)
from prediction_market_agent_tooling.tools.utils import DatetimeUTC, check_not_none


class MetaculusAgentMarket(AgentMarket):
    """
    Metaculus' market class that can be used by agents to make predictions.
    """

    have_predicted: bool
    base_url: t.ClassVar[str] = METACULUS_API_BASE_URL
    description: str
    fine_print: str
    resolution_criteria: str
    fees: MarketFees = MarketFees.get_zero_fees()  # No fees on Metaculus.

    @field_validator("probabilities")
    def validate_probabilities(
        cls,
        probs: dict[OutcomeStr, Probability],
        info: FieldValidationInfo,
    ) -> dict[OutcomeStr, Probability]:
        # We don't check for outcomes match here because Metaculus has no filled outcomes.
        return probs

    @staticmethod
    def from_data_model(model: MetaculusQuestion) -> "MetaculusAgentMarket":
        probabilities = AgentMarket.build_probability_map_from_p_yes(p_yes=model.p_yes)
        return MetaculusAgentMarket(
            id=str(model.id),
            question=model.title,
            outcomes=[],
            resolution=None,
            created_time=model.created_at,
            close_time=model.scheduled_close_time,
            url=model.page_url,
            volume=None,
            have_predicted=model.question.my_forecasts.latest is not None,
            outcome_token_pool=None,
            description=model.question.description,
            fine_print=model.question.fine_print,
            resolution_criteria=model.question.resolution_criteria,
            probabilities=probabilities,
        )

    @staticmethod
    def get_markets(
        limit: int,
        sort_by: SortBy = SortBy.NONE,
        filter_by: FilterBy = FilterBy.OPEN,
        created_after: t.Optional[DatetimeUTC] = None,
        excluded_questions: set[str] | None = None,
        market_type: MarketType = MarketType.ALL,
        include_conditional_markets: bool = False,
        tournament_id: int | None = None,
    ) -> t.Sequence["MetaculusAgentMarket"]:
        order_by: str | None
        if sort_by == SortBy.NONE:
            order_by = None
        elif sort_by == SortBy.CLOSING_SOONEST:
            order_by = "-close_time"
        elif sort_by == SortBy.NEWEST:
            order_by = "-created_time"
        else:
            raise ValueError(f"Unknown sort_by: {sort_by}")

        status: str | None
        if filter_by == FilterBy.OPEN:
            status = "open"
        elif filter_by == FilterBy.RESOLVED:
            status = "resolved"
        elif filter_by == FilterBy.NONE:
            status = None
        else:
            raise ValueError(f"Unknown filter_by: {filter_by}")

        if excluded_questions:
            raise NotImplementedError(
                "Excluded questions are not suppoerted for Metaculus markets yet."
            )

        offset = 0
        question_page_size = 500
        all_questions = []
        while True:
            questions = get_questions(
                limit=question_page_size,
                offset=offset,
                order_by=order_by,
                created_after=created_after,
                status=status,
                tournament_id=tournament_id,
            )
            if not questions:
                break
            all_questions.extend(questions)
            offset += question_page_size

            if len(all_questions) >= limit:
                break
        return [MetaculusAgentMarket.from_data_model(q) for q in all_questions[:limit]]

    def store_prediction(
        self, processed_market: ProcessedMarket | None, keys: APIKeys, agent_name: str
    ) -> None:
        if (
            processed_market is not None
            and processed_market.answer.get_yes_probability() is not None
        ):
            yes_prob = check_not_none(processed_market.answer.get_yes_probability())
            make_prediction(self.id, yes_prob)
            post_question_comment(
                self.id,
                check_not_none(
                    processed_market.answer.reasoning,
                    "Reasoning must be provided for Metaculus.",
                ),
            )

    @staticmethod
    def get_user_id(api_keys: APIKeys) -> str:
        return str(api_keys.metaculus_user_id)

    @staticmethod
    def verify_operational_balance(api_keys: APIKeys) -> bool:
        # No operational balance for Metaculus.
        return True

    @staticmethod
    def redeem_winnings(api_keys: APIKeys) -> None:
        # Nothing to redeem on Metaculus.
        pass
