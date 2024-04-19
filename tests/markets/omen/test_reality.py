from datetime import timedelta

import pytest
from loguru import logger

from prediction_market_agent_tooling.config import APIKeys, PrivateCredentials
from prediction_market_agent_tooling.markets.omen.omen_contracts import (
    Arbitrator,
    OmenRealitioContract,
)
from prediction_market_agent_tooling.tools.utils import utcnow
from tests.utils import RUN_PAID_TESTS


@pytest.mark.skipif(not RUN_PAID_TESTS, reason="This test costs money to run.")
def test_ask_question() -> None:
    keys = APIKeys()
    private_credentials = PrivateCredentials.from_api_keys(keys)
    realitio_contract = OmenRealitioContract()
    question_id = realitio_contract.askQuestion(
        private_credentials=private_credentials,
        question="Will GNO be above $1000 in 2 minutes from now?",
        category="cryptocurrency",
        outcomes=["Yes", "No"],
        language="en",
        arbitrator=Arbitrator.KLEROS,
        opening=utcnow() + timedelta(minutes=2),
    )
    logger.info(question_id)
