import requests

from prediction_market_agent_tooling.gtypes import HexBytes
from prediction_market_agent_tooling.markets.omen.data_models import (
    RealityAnswer,
    RealityAnswersResponse,
)
from prediction_market_agent_tooling.tools.utils import response_to_model

REALITYETH_GRAPH_URL = (
    "https://api.thegraph.com/subgraphs/name/realityeth/realityeth-gnosis"
)


_QUERY_GET_ANSWERS = """
query getAnswers($question_id: String!) {
    answers(
        where: {
            question_: {questionId: $question_id}
        }
    ) {
        answer
        question {
            historyHash
            id
            user
            updatedTimestamp
            questionId
        }
        bondAggregate
        lastBond
        timestamp
    }
}
"""


def reality_get_answers(question_id: HexBytes) -> list[RealityAnswer]:
    return response_to_model(
        requests.post(
            REALITYETH_GRAPH_URL,
            json={
                "query": _QUERY_GET_ANSWERS,
                "variables": {
                    "question_id": question_id.hex(),
                },
            },
            headers={"Content-Type": "application/json"},
        ),
        RealityAnswersResponse,
    ).data.answers
