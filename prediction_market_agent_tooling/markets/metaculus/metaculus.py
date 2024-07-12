import typing as t
from datetime import datetime

from prediction_market_agent_tooling.gtypes import Probability
from prediction_market_agent_tooling.markets.agent_market import (
    AgentMarket,
    FilterBy,
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


class MetaculusAgentMarket(AgentMarket):
    """
    Metaculus' market class that can be used by agents to make predictions.
    """

    have_predicted: bool
    base_url: t.ClassVar[str] = METACULUS_API_BASE_URL
    description: str | None = (
        None  # Metaculus markets don't have a description, so just default to None.
    )

    @staticmethod
    def from_data_model(model: MetaculusQuestion) -> "MetaculusAgentMarket":
        return MetaculusAgentMarket(
            id=str(model.id),
            question=model.title,
            outcomes=[],
            resolution=None,
            current_p_yes=Probability(model.community_prediction.full.p_yes),
            created_time=model.created_time,
            close_time=model.close_time,
            url=model.url,
            volume=None,
            have_predicted=model.my_predictions is not None
            and len(model.my_predictions.predictions) > 0,
        )

    @staticmethod
    def get_binary_markets(
        limit: int,
        sort_by: SortBy = SortBy.NONE,
        filter_by: FilterBy = FilterBy.OPEN,
        created_after: t.Optional[datetime] = None,
        excluded_questions: set[str] | None = None,
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
        return [MetaculusAgentMarket.from_data_model(q) for q in all_questions]

    def submit_prediction(self, p_yes: Probability, reasoning: str) -> None:
        make_prediction(self.id, p_yes)
        post_question_comment(self.id, reasoning)
