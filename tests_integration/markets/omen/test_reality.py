import time
from datetime import timedelta

import pytest

from prediction_market_agent_tooling.config import APIKeys
from prediction_market_agent_tooling.gtypes import HexBytes, wei_type, xdai_type
from prediction_market_agent_tooling.loggers import logger
from prediction_market_agent_tooling.markets.omen.omen_contracts import (
    Arbitrator,
    OmenRealitioContract,
)
from prediction_market_agent_tooling.markets.omen.omen_resolving import (
    claim_bonds_on_realitio_question,
)
from prediction_market_agent_tooling.markets.omen.omen_subgraph_handler import (
    OmenSubgraphHandler,
)
from prediction_market_agent_tooling.tools.utils import utcnow
from prediction_market_agent_tooling.tools.web3_utils import xdai_to_wei
from tests.utils import RUN_PAID_TESTS


@pytest.mark.skipif(not RUN_PAID_TESTS, reason="This test costs money to run.")
def test_claim_bonds() -> None:
    api_keys = APIKeys()
    realitio_contract = OmenRealitioContract()
    timeout = timedelta(seconds=60)
    outcomes = ["Yes", "No"]

    # Ask a question
    question_id = realitio_contract.askQuestion(
        api_keys=api_keys,
        question="Will GNO be above $1000 in 1 second from now?",
        category="cryptocurrency",
        outcomes=outcomes,
        language="en",
        arbitrator=Arbitrator.KLEROS,
        opening=utcnow() + timedelta(seconds=1),
        timeout=timeout,
    )
    logger.info(f"Question ID: {question_id.hex()}")
    time.sleep(2)  # Wait for the question to be opened.

    # Add multiple answers
    bond = xdai_to_wei(xdai_type(0.00001))
    answers = [outcomes[0], outcomes[1], outcomes[0]]
    for answer in answers:
        realitio_contract.submit_answer(
            api_keys=api_keys,
            question_id=question_id,
            answer=answer,
            outcomes=outcomes,
            bond=bond,
        )
        bond = wei_type(bond * 2)
        logger.info(f"Answered with: {answer}")
        time.sleep(2)  # Give it a moment to settle on chain.

    time.sleep(timeout.total_seconds() + 2)  # Wait for the question to be finalized.

    question_id = HexBytes(
        "0x9821f98b66c4cb079157b63823ab66aaadfca7e3e023562f9caba28f576f7674"
    )

    # Try to claim bonds
    question = OmenSubgraphHandler().get_questions(question_id_in=[question_id])[0]
    logger.info(f"Claiming for {question.url}")
    claim_bonds_on_realitio_question(
        api_keys=api_keys,
        question=question,
        auto_withdraw=True,
    )
