from prediction_market_agent_tooling.gtypes import HexBytes
from prediction_market_agent_tooling.tools.utils import response_to_model
import requests
from prediction_market_agent_tooling.markets.omen.data_models import (
    RealityAnswersResponse,
)

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


def reality_get_answers(question_id: HexBytes) -> RealityAnswersResponse:
    return response_to_model(
        requests.post(
            REALITYETH_GRAPH_URL,
            json={
                "query": _QUERY_GET_ANSWERS,
                "variables": {
                    "question_id": question_id.hex(,)
                },
            },
            headers={"Content-Type": "application/json"},
        ),
        RealityAnswersResponse,
    )


question_id = HexBytes(
    b"U0\xfbk\xb4X\xa3\xde\xd0\x90\x82\xfe\xf3\x19\xfa\xd6\x01\xf3\xf1\xe0\x8e\xe6\xddF \xc1,% \xccN\r"
)

print(reality_get_answers(question_id))
