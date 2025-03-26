from prediction_market_agent_tooling.gtypes import OutcomeStr
from prediction_market_agent_tooling.markets.omen.data_models import (
    ParsedQuestion,
    format_realitio_question,
    parse_realitio_question,
)


def test_format_and_decode_question() -> None:
    question = ParsedQuestion(
        question="How are you?",
        outcomes=[OutcomeStr("Cool"), OutcomeStr("Not cool")],
        language="en",
        category="life",
    )
    formatted = format_realitio_question(
        question.question, question.outcomes, question.category, question.language, 2
    )
    parsed = parse_realitio_question(formatted, 2)
    assert parsed == question
