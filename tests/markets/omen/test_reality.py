from prediction_market_agent_tooling.markets.omen.omen_contracts import (
    OmenRealitioContract,
    Arbitrator,
)
from prediction_market_agent_tooling.config import APIKeys
from datetime import timedelta
import pytest
from tests.utils import RUN_PAID_TESTS
from prediction_market_agent_tooling.tools.utils import utcnow


@pytest.mark.skipif(not RUN_PAID_TESTS, reason="This test costs money to run.")
def test_ask_question() -> None:
    realitio_contract = OmenRealitioContract()
    question_id = realitio_contract.askQuestion(
        question="Will GNO be above $1000 in 2 minutes from now?",
        category="cryptocurrency",
        outcomes=["Yes", "No"],
        language="en",
        arbitrator=Arbitrator.KLEROS,
        opening=utcnow() + timedelta(minutes=2),
        from_private_key=APIKeys().bet_from_private_key,
    )
    print(question_id)
