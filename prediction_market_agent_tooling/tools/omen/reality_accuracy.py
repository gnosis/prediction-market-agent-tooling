from datetime import timedelta

from pydantic import BaseModel

from prediction_market_agent_tooling.markets.omen.omen_subgraph_handler import (
    ChecksumAddress,
    OmenSubgraphHandler,
    RealityResponse,
)
from prediction_market_agent_tooling.tools.utils import utcnow


class RealityAccuracyReport(BaseModel):
    total: int
    correct: int

    @property
    def accuracy(self) -> float:
        return self.correct / self.total


def reality_accuracy(user: ChecksumAddress, since: timedelta) -> RealityAccuracyReport:
    now = utcnow()
    start_from = now - since

    # Get all question ids where we placed the higher bond.
    user_responses = OmenSubgraphHandler().get_responses(
        limit=None,
        user=user,
        question_finalized_before=now,
        question_finalized_after=start_from,
    )
    unique_question_ids = set(r.question.questionId for r in user_responses)

    # Get all responses for these questions (including not ours)
    question_to_responses = {
        question_id: OmenSubgraphHandler().get_responses(
            limit=None, question_id=question_id
        )
        for question_id in unique_question_ids
    }

    total = 0
    correct = 0

    for question_id, responses in question_to_responses.items():
        is_correct = user_was_correct(user, responses)
        assert (
            is_correct is not None
        ), f"All these questions should be challenged by provded user: {responses[0].question.url}"

        total += 1
        correct += int(is_correct)

    return RealityAccuracyReport(total=total, correct=correct)


def user_was_correct(
    user: ChecksumAddress, responses: list[RealityResponse]
) -> bool | None:
    sorted_responses = sorted(responses, key=lambda r: r.timestamp)
    users_sorted_responses = [r for r in sorted_responses if r.user_checksummed == user]

    if not users_sorted_responses:
        return None

    # Find the user's last response
    users_last_response = users_sorted_responses[-1]

    # Last response is the final one (if market is finalized)
    actual_resolution = sorted_responses[-1]

    # Compare the user's last answer with the actual resolution
    return users_last_response.answer == actual_resolution.answer
