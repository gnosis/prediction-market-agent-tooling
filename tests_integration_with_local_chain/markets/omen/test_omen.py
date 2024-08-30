import os
import time
from datetime import timedelta

import numpy as np
import pytest
from ape_test import TestAccount
from pydantic import SecretStr
from web3 import Web3

from prediction_market_agent_tooling.config import APIKeys
from prediction_market_agent_tooling.deploy.agent_example import (
    DeployableAlwaysYesAgent,
)
from prediction_market_agent_tooling.gtypes import (
    ChecksumAddress,
    HexAddress,
    HexStr,
    xDai,
    xdai_type,
)
from prediction_market_agent_tooling.loggers import logger
from prediction_market_agent_tooling.markets.data_models import (
    BetAmount,
    Currency,
    TokenAmount,
    Position,
)
from prediction_market_agent_tooling.markets.markets import MarketType
from prediction_market_agent_tooling.markets.omen.data_models import (
    OMEN_FALSE_OUTCOME,
    OMEN_TRUE_OUTCOME,
)
from prediction_market_agent_tooling.markets.omen.omen import (
    OmenAgentMarket,
    binary_omen_buy_outcome_tx,
    omen_create_market_tx,
    omen_fund_market_tx,
    omen_redeem_full_position_tx,
    omen_remove_fund_market_tx,
    pick_binary_market,
)
from prediction_market_agent_tooling.markets.omen.omen_contracts import (
    OMEN_DEFAULT_MARKET_FEE,
    ContractDepositableWrapperERC20OnGnosisChain,
    OmenFixedProductMarketMakerContract,
    OmenRealitioContract,
    WrappedxDaiContract,
    sDaiContract,
)
from prediction_market_agent_tooling.markets.omen.omen_subgraph_handler import (
    OmenSubgraphHandler,
)
from prediction_market_agent_tooling.tools.balances import get_balances
from prediction_market_agent_tooling.tools.utils import utcnow
from prediction_market_agent_tooling.tools.web3_utils import xdai_to_wei

DEFAULT_REASON = "Test logic need to be rewritten for usage of local chain, see ToDos"


def is_contract(web3: Web3, contract_address: ChecksumAddress) -> bool:
    # From gnosis.eth.EthereumClient
    return bool(web3.eth.get_code(contract_address))


@pytest.mark.skip(reason=DEFAULT_REASON)
def test_create_bet_withdraw_resolve_market(
    local_web3: Web3,
    test_keys: APIKeys,
) -> None:
    omen_subgraph_handler = OmenSubgraphHandler()
    wait_time = 60

    # Create a market with a very soon to be resolved question that will most probably be No.
    question = f"Will GNO be above $10000 in {wait_time} seconds from now?"
    closing_time = utcnow() + timedelta(seconds=wait_time)

    market_address = omen_create_market_tx(
        api_keys=test_keys,
        initial_funds=xdai_type(0.001),
        fee=OMEN_DEFAULT_MARKET_FEE,
        question=question,
        closing_time=closing_time,
        category="cryptocurrency",
        language="en",
        outcomes=[OMEN_TRUE_OUTCOME, OMEN_FALSE_OUTCOME],
        auto_deposit=True,
        web3=local_web3,
    )
    logger.debug(f"Market created at address: {market_address}")
    # ToDo - Fix call here (subgraph will not update on localchain). Retrieve data directly from contract.
    market = omen_subgraph_handler.get_omen_market_by_market_id(market_address)

    # Double check the market was created correctly.
    assert market.question_title == question

    # Bet on the false outcome.
    logger.debug("Betting on the false outcome.")
    agent_market = OmenAgentMarket.from_data_model(market)

    binary_omen_buy_outcome_tx(
        api_keys=test_keys,
        amount=xdai_type(0.001),
        market=agent_market,
        binary_outcome=False,
        auto_deposit=True,
    )

    # TODO: Add withdraw funds from the market.

    # Wait until the realitio question is opened (== market is closed).
    logger.debug("Waiting for the market to close.")
    time.sleep(wait_time)

    # Submit the answer and verify it was successfully submitted.
    logger.debug(f"Submitting the answer to {market.question.id=}.")

    OmenRealitioContract().submit_answer(
        api_keys=test_keys,
        question_id=market.question.id,
        answer=OMEN_FALSE_OUTCOME,
        outcomes=market.question.outcomes,
        bond=xdai_to_wei(xDai(0.001)),
    )

    # ToDo - Instead of subgraph, fetch data directly from contract.
    answers = omen_subgraph_handler.get_answers(market.question.id)
    assert len(answers) == 1, answers
    # ToDo: Once this test is fixed, check how to assert this, currently `answer` is HexBytes and OMEN_FALSE_OUTCOME is string, so it will never be equal.
    # assert answers[0].answer == OMEN_FALSE_OUTCOME, answers[0]

    # Note: We can not redeem the winning bet here, because the answer gets settled in 24 hours.
    # The same goes about claiming bonded xDai on Realitio.


def test_omen_create_market_wxdai(
    local_web3: Web3,
    test_keys: APIKeys,
) -> None:
    market_address = omen_create_market_tx(
        api_keys=test_keys,
        initial_funds=xdai_type(0.001),
        question="Will GNO hit $1000 in 2 minutes from creation of this market?",
        closing_time=utcnow() + timedelta(minutes=2),
        category="cryptocurrency",
        language="en",
        outcomes=[OMEN_TRUE_OUTCOME, OMEN_FALSE_OUTCOME],
        auto_deposit=True,
        web3=local_web3,
    )
    assert is_contract(local_web3, market_address)
    market_contract = OmenFixedProductMarketMakerContract(address=market_address)
    assert (
        market_contract.collateralToken(web3=local_web3)
        == WrappedxDaiContract().address
    )


def test_omen_create_market_sdai(
    local_web3: Web3,
    test_keys: APIKeys,
) -> None:
    market_address = omen_create_market_tx(
        api_keys=test_keys,
        initial_funds=xdai_type(100),
        question="Will GNO hit $1000 in 2 minutes from creation of this market?",
        closing_time=utcnow() + timedelta(minutes=2),
        category="cryptocurrency",
        language="en",
        outcomes=[OMEN_TRUE_OUTCOME, OMEN_FALSE_OUTCOME],
        auto_deposit=True,
        collateral_token_address=sDaiContract().address,
        web3=local_web3,
    )
    assert is_contract(local_web3, market_address)
    market_contract = OmenFixedProductMarketMakerContract(address=market_address)
    assert market_contract.collateralToken(web3=local_web3) == sDaiContract().address


@pytest.mark.skip(reason=DEFAULT_REASON)
def test_omen_redeem_positions(
    local_web3: Web3,
    test_keys: APIKeys,
) -> None:
    # ToDo - create local chain with a given block B, where B is a block where a given agent had funds in the market.
    #  Then, create keys for that agent instead of relying on test_keys.
    market_id = (
        "0x6469da5478e5b2ddf9f6b7fba365e5670b7880f4".lower()
    )  # Market on which agent previously betted on
    subgraph_handler = OmenSubgraphHandler()
    market_data_model = subgraph_handler.get_omen_market_by_market_id(
        market_id=HexAddress(HexStr(market_id))
    )
    market = OmenAgentMarket.from_data_model(market_data_model)

    omen_redeem_full_position_tx(api_keys=test_keys, market=market, web3=local_web3)


@pytest.mark.skip(reason=DEFAULT_REASON)
def test_create_market_fund_market_remove_funding() -> None:
    """
    ToDo - Once we have tests running in an isolated blockchain, write this test as follows:
        - Create a new market
        - Fund the market with amount
        - Assert balanceOf(creator) == amount
        - (Optionally) Close the market
        - Remove funding
        - Assert amount in xDAI is reflected in user's balance
    """
    assert False


def test_balance_for_user_in_market() -> None:
    user_address = Web3.to_checksum_address(
        "0x2DD9f5678484C1F59F97eD334725858b938B4102"
    )
    market_id = "0x59975b067b0716fef6f561e1e30e44f606b08803"
    market = OmenAgentMarket.get_binary_market(market_id)
    balance_yes: TokenAmount = market.get_token_balance(
        user_id=user_address,
        outcome=OMEN_TRUE_OUTCOME,
    )
    assert balance_yes.currency == Currency.xDai
    assert float(balance_yes.amount) == 0

    balance_no = market.get_token_balance(
        user_id=user_address,
        outcome=OMEN_FALSE_OUTCOME,
    )
    assert balance_no.currency == Currency.xDai
    assert float(balance_no.amount) == 0


def test_omen_fund_and_remove_fund_market(
    local_web3: Web3,
    test_keys: APIKeys,
) -> None:
    # You can double check your address at https://gnosisscan.io/ afterwards or at the market's address.
    market = OmenAgentMarket.from_data_model(pick_binary_market())
    logger.debug(
        "Fund and remove funding market test address:",
        market.market_maker_contract_address_checksummed,
    )

    funds = xdai_to_wei(xdai_type(0.1))
    remove_fund = xdai_to_wei(xdai_type(0.01))

    omen_fund_market_tx(
        api_keys=test_keys,
        market=market,
        funds=funds,
        auto_deposit=True,
        web3=local_web3,
    )

    omen_remove_fund_market_tx(
        api_keys=test_keys,
        market=market,
        shares=remove_fund,
        web3=local_web3,
    )


def test_omen_buy_and_sell_outcome(
    local_web3: Web3,
    test_keys: APIKeys,
) -> None:
    # Tests both buying and selling, so we are back at the square one in the wallet (minues fees).
    # You can double check your address at https://gnosisscan.io/ afterwards.
    market = OmenAgentMarket.from_data_model(pick_binary_market())
    outcome = True
    outcome_str = OmenAgentMarket.get_bet_outcome(outcome)
    bet_amount = market.get_bet_amount(amount=0.4)

    # TODO hack until https://github.com/gnosis/prediction-market-agent-tooling/issues/266 is complete
    os.environ[
        "BET_FROM_PRIVATE_KEY"
    ] = test_keys.bet_from_private_key.get_secret_value()
    api_keys = APIKeys()

    def get_market_outcome_tokens() -> TokenAmount:
        return market.get_token_balance(
            user_id=api_keys.bet_from_address,
            outcome=outcome_str,
            web3=local_web3,
        )

    # Check our wallet has sufficient funds
    balances = get_balances(address=api_keys.bet_from_address, web3=local_web3)
    assert balances.xdai + balances.wxdai > bet_amount.amount

    market.place_bet(outcome=outcome, amount=bet_amount, web3=local_web3)

    # Check that we now have a position in the market.
    outcome_tokens = get_market_outcome_tokens()
    assert outcome_tokens.amount > 0

    market.sell_tokens(
        outcome=outcome,
        amount=outcome_tokens,
        web3=local_web3,
        api_keys=api_keys,
    )

    # Check that we have sold our entire stake in the market.
    remaining_tokens = get_market_outcome_tokens()
    assert np.isclose(remaining_tokens.amount, 0, atol=1e-5)


def test_place_bet_with_autodeposit(
    local_web3: Web3,
    test_keys: APIKeys,
) -> None:
    market = OmenAgentMarket.from_data_model(pick_binary_market())
    initial_balances = get_balances(address=test_keys.bet_from_address, web3=local_web3)
    collateral_token_contract = market.get_contract().get_collateral_token_contract()
    assert (
        collateral_token_contract.symbol() == "WXDAI"
    ), "Should have retrieve wxDai market."
    assert isinstance(
        collateral_token_contract, ContractDepositableWrapperERC20OnGnosisChain
    ), "wxDai market should adhere to this class."

    # Start by moving all funds from wxdai to xdai
    if initial_balances.wxdai > 0:
        collateral_token_contract.withdraw(
            api_keys=test_keys,
            amount_wei=xdai_to_wei(initial_balances.wxdai),
            web3=local_web3,
        )

    # Check that we have xdai funds, but no wxdai funds
    initial_balances = get_balances(address=test_keys.bet_from_address, web3=local_web3)
    assert initial_balances.wxdai == xdai_type(0)
    assert initial_balances.xdai > xdai_type(0)

    # Convert half of the xDai to wxDai
    collateral_token_contract.deposit(
        api_keys=test_keys,
        amount_wei=xdai_to_wei(xdai_type(initial_balances.xdai * 0.5)),
        web3=local_web3,
    )
    new_balances = get_balances(address=test_keys.bet_from_address, web3=local_web3)
    assert np.allclose(new_balances.total, initial_balances.total)

    # Try to place a bet with 90% of the xDai funds
    bet_amount = BetAmount(amount=initial_balances.xdai * 0.9, currency=Currency.xDai)
    assert new_balances.xdai < bet_amount.amount
    assert new_balances.wxdai < bet_amount.amount
    assert new_balances.total > bet_amount.amount
    market.place_bet(
        outcome=True,
        amount=bet_amount,
        omen_auto_deposit=True,
        web3=local_web3,
        api_keys=test_keys,
    )


def test_place_bet_with_prev_existing_positions(
    local_web3: Web3,
    test_keys: APIKeys,
    accounts: list[TestAccount],
) -> None:
    # ToDo get a open binary market where better has a position
    # place bet on contrary outcome (amount X)
    # assert bet amount is X + prev_position_amount

    m = OmenSubgraphHandler().get_omen_market_by_market_id(market_id)
    market = OmenAgentMarket.from_data_model(m)

    # sell prev False positions
    market.sell_existing_positions(False)

    # place a bet of 1 wxDAI on YES
    bet_amount = BetAmount(amount=xdai_to_wei(xDai(1)), currency=Currency.xDai)
    # account 0xe7aa88a1d044e5c987ecce55ae8d2b562a41b72d
    # private d459e4b81c6daaef4a34ade0b15f30b99ce486efdc44fcb869481668f5c8f66b
    private_key = "d459e4b81c6daaef4a34ade0b15f30b99ce486efdc44fcb869481668f5c8f66b"

    keys = APIKeys(BET_FROM_PRIVATE_KEY=SecretStr(private_key), SAFE_ADDRESS=None)

    # ToDo # assert that 2nd bet had size 2 wxDAI - call contract directly
    positions = market.get_positions(
        user_id=test_keys.bet_from_address, liquid_only=True
    )
    position_in_market: Position = next(
        [i for i in positions if i.market_id == market.id]
    )
    assert position_in_market
    # # assert final user position is only on outcome NO
    assert position_in_market.amounts[OMEN_FALSE_OUTCOME] == xDai(2)
    assert position_in_market.amounts[OMEN_TRUE_OUTCOME] == xDai(0)
