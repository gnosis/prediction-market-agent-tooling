from datetime import timedelta

import pytest
from web3 import Web3

from prediction_market_agent_tooling.config import APIKeys
from prediction_market_agent_tooling.markets.omen.omen_contracts import (
    Arbitrator,
    OmenRealitioContract,
)
from prediction_market_agent_tooling.tools.utils import utcnow


@pytest.mark.parametrize(
    "arbitrator",
    [
        Arbitrator.KLEROS_511_JURORS_WITHOUT_APPEAL,
        Arbitrator.KLEROS_31_JURORS_WITH_APPEAL,
        Arbitrator.DXDAO,
    ],
)
def test_ask_question(
    arbitrator: Arbitrator, local_web3: Web3, test_keys: APIKeys
) -> None:
    realitio_contract = OmenRealitioContract()
    question_id = realitio_contract.askQuestion(
        api_keys=test_keys,
        question="Will GNO be above $1000 in 2 minutes from now?",
        category="cryptocurrency",
        outcomes=["Yes", "No"],
        language="en",
        arbitrator=arbitrator,
        opening=utcnow() + timedelta(minutes=2),
        timeout=timedelta(seconds=5),
        web3=local_web3,
    )
    assert question_id is not None
