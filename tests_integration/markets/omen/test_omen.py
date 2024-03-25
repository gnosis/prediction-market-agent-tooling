import time
from datetime import timedelta

import pytest

from prediction_market_agent_tooling.config import APIKeys
from prediction_market_agent_tooling.gtypes import xdai_type
from prediction_market_agent_tooling.markets.omen.data_models import (
    OMEN_FALSE_OUTCOME,
    OMEN_TRUE_OUTCOME,
)
from prediction_market_agent_tooling.markets.omen.omen import (
    OMEN_DEFAULT_MARKET_FEE,
    OmenAgentMarket,
    binary_omen_buy_outcome_tx,
    get_market,
    omen_create_market_tx,
)
from prediction_market_agent_tooling.markets.omen.omen_contracts import (
    HexBytes,
    OmenRealitioContract,
)
from prediction_market_agent_tooling.markets.omen.reality_subgraph import (
    reality_get_answers,
)
from prediction_market_agent_tooling.tools.contract import wait_until_nonce_changed
from prediction_market_agent_tooling.tools.utils import utcnow
from prediction_market_agent_tooling.tools.web3_utils import xdai_to_wei
from tests.utils import RUN_PAID_TESTS


@pytest.mark.skipif(not RUN_PAID_TESTS, reason="This test costs money to run.")
def test_create_bet_withdraw_resolve_market() -> None:
    wait_time = 60
    keys = APIKeys()

    # Create a market with a very soon to be resolved question that will most probably be No.
    question = f"Will GNO be above $10000 in {wait_time} seconds from now?"
    closing_time = utcnow() + timedelta(seconds=wait_time)
    with wait_until_nonce_changed(for_address=keys.bet_from_address):
        market_address = omen_create_market_tx(
            initial_funds=xdai_type(0.001),
            fee=OMEN_DEFAULT_MARKET_FEE,
            question=question,
            closing_time=closing_time,
            category="cryptocurrency",
            language="en",
            from_private_key=keys.bet_from_private_key,
            outcomes=[OMEN_TRUE_OUTCOME, OMEN_FALSE_OUTCOME],
            auto_deposit=True,
        )
    print(f"Market created at address: {market_address}")
    market = get_market(market_address)

    # Double check the market was created correctly.
    assert market.question_title == question

    # Bet on the false outcome.
    print("Betting on the false outcome.")
    agent_market = OmenAgentMarket.from_data_model(market)
    with wait_until_nonce_changed(for_address=keys.bet_from_address):
        binary_omen_buy_outcome_tx(
            amount=xdai_type(0.001),
            from_private_key=keys.bet_from_private_key,
            market=agent_market,
            binary_outcome=False,
            auto_deposit=True,
        )

    # TODO: Add withdraw funds from the market.

    # Wait until the realitio question is opened (== market is closed).
    print("Waiting for the market to close.")
    time.sleep(wait_time)

    # Submit the answer and verify it was successfully submitted.
    print(f"Submitting the answer to {market.question.id=}.")
    with wait_until_nonce_changed(for_address=keys.bet_from_address):
        OmenRealitioContract().submitAnswer(
            question_id=HexBytes(market.question.id),  # TODO: Remove HexBytes.
            answer=OMEN_FALSE_OUTCOME,
            outcomes=market.question.outcomes,
            bond=xdai_to_wei(0.001),
            from_private_key=APIKeys().bet_from_private_key,
        )
    answers = reality_get_answers(
        HexBytes(market.question.id)
    )  # TODO: Remove HexBytes.
    assert len(answers) == 1, answers
    assert answers[0].answer == OMEN_FALSE_OUTCOME, answers[0]

    # Note: We can not redeem the winning bet here, because the answer gets settled in 24 hours.
    # The same goes about claiming bonded xDai on Realitio.
