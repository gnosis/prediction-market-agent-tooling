from datetime import timedelta

from web3 import Web3

from prediction_market_agent_tooling.config import APIKeys
from prediction_market_agent_tooling.markets.omen.omen_contracts import (
    Arbitrator,
    OmenRealitioContract,
)
from prediction_market_agent_tooling.tools.utils import utcnow


def test_ask_question(local_web3: Web3, test_keys: APIKeys) -> None:
    realitio_contract = OmenRealitioContract()
    question_id = realitio_contract.askQuestion(
        api_keys=test_keys,
        question="Will GNO be above $1000 in 2 minutes from now?",
        category="cryptocurrency",
        outcomes=["Yes", "No"],
        language="en",
        arbitrator=Arbitrator.KLEROS,
        opening=utcnow() + timedelta(minutes=2),
        timeout=timedelta(seconds=5),
        web3=local_web3,
    )
    assert question_id is not None
