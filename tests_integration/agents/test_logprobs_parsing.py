import pytest
from openai import OpenAI
from pydantic import BaseModel

from prediction_market_agent_tooling.config import APIKeys
from prediction_market_agent_tooling.logprobs_parser import LogprobsParser
from tests.utils import RUN_PAID_TESTS


class DummyModel(BaseModel):
    greet: str


@pytest.mark.skipif(not RUN_PAID_TESTS, reason="This test costs money to run.")
def test_logprobs_parsing() -> None:
    api_keys = APIKeys()
    client = OpenAI(api_key=api_keys.openai_api_key.get_secret_value())

    response = client.chat.completions.create(
        model="gpt-4o",
        messages=[
            {
                "role": "user",
                "content": "Respond EXACTLY with a greeting in format greet: <greeting>",
            }
        ],
        logprobs=True,
        top_logprobs=3,
    )
    parser = LogprobsParser([])
    logprobs = response.choices[0].logprobs

    assert logprobs is not None
    assert logprobs.content is not None

    # TODO: this is done by PydanticAI agent, we have to use it after they add logprobs
    dict_logprobs = [logprob.model_dump() for logprob in logprobs.content]
    result = parser.parse_logprobs(dict_logprobs, DummyModel)

    assert len(result) > 0
    assert result[0].key is not None
    assert result[0].logprobs is not None
    assert result[0].logprobs[0].token is not None
    assert result[0].logprobs[0].prob is not None
    assert result[0].logprobs[0].logprob is not None
