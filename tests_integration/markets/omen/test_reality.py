import time
from datetime import timedelta

import pytest

from prediction_market_agent_tooling.config import APIKeys
from prediction_market_agent_tooling.gtypes import OutcomeStr, xDai
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
from tests.utils import RUN_PAID_TESTS


@pytest.mark.skipif(not RUN_PAID_TESTS, reason="This test costs money to run.")
def test_claim_bonds() -> None:
    api_keys = APIKeys()
    realitio_contract = OmenRealitioContract()
    timeout = timedelta(seconds=60)
    outcomes = [OutcomeStr("Yes"), OutcomeStr("No")]

    # Ask a question
    question_event = realitio_contract.askQuestion(
        api_keys=api_keys,
        question="Will GNO be above $1000 in 1 second from now?",
        category="cryptocurrency",
        outcomes=outcomes,
        language="en",
        arbitrator=Arbitrator.KLEROS_31_JURORS_WITH_APPEAL,
        opening=utcnow() + timedelta(seconds=1),
        timeout=timeout,
    )
    logger.info(f"Question ID: {question_event.question_id.hex()}")
    time.sleep(2)  # Wait for the question to be opened.

    # Add multiple answers
    bond = xDai(0.00001).as_xdai_wei
    outcome_idxs = [0, 1, 0, 1]

    for idx in outcome_idxs:
        realitio_contract.submit_answer(
            api_keys=api_keys,
            question_id=question_event.question_id,
            outcome_index=idx,
            bond=bond,
        )
        bond *= 2
        logger.info(f"Answered with: {outcomes[idx]}")
        time.sleep(2)  # Give it a moment to settle on chain.

    time.sleep(timeout.total_seconds() + 2)  # Wait for the question to be finalized.

    # Try to claim bonds
    question = OmenSubgraphHandler().get_questions(
        limit=1, question_id_in=[question_event.question_id]
    )[0]
    logger.info(f"Claiming for {question.url}")
    claim_bonds_on_realitio_question(
        api_keys=api_keys,
        question=question,
        auto_withdraw=True,
    )
