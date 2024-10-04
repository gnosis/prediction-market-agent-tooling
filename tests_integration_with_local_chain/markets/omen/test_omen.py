import os
import time
from datetime import timedelta
from unittest.mock import patch

import numpy as np
import pytest
from web3 import Web3
from web3.constants import HASH_ZERO

from prediction_market_agent_tooling.config import APIKeys
from prediction_market_agent_tooling.gtypes import (
    ChecksumAddress,
    HexAddress,
    HexStr,
    OutcomeStr,
    Wei,
    private_key_type,
    xDai,
    xdai_type,
)
from prediction_market_agent_tooling.loggers import logger
from prediction_market_agent_tooling.markets.agent_market import FilterBy, SortBy
from prediction_market_agent_tooling.markets.data_models import (
    BetAmount,
    Currency,
    Position,
    TokenAmount,
)
from prediction_market_agent_tooling.markets.omen.data_models import (
    OMEN_BINARY_MARKET_OUTCOMES,
    OMEN_FALSE_OUTCOME,
    OMEN_TRUE_OUTCOME,
    ContractPrediction,
    get_bet_outcome,
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
    OMEN_DEFAULT_MARKET_FEE_PERC,
    ContractDepositableWrapperERC20OnGnosisChain,
    ContractERC4626OnGnosisChain,
    OmenAgentResultMappingContract,
    OmenConditionalTokenContract,
    OmenFixedProductMarketMakerContract,
    OmenRealitioContract,
    WrappedxDaiContract,
    sDaiContract,
)
from prediction_market_agent_tooling.markets.omen.omen_subgraph_handler import (
    OmenSubgraphHandler,
)
from prediction_market_agent_tooling.tools.balances import get_balances
from prediction_market_agent_tooling.tools.hexbytes_custom import HexBytes
from prediction_market_agent_tooling.tools.utils import utcnow
from prediction_market_agent_tooling.tools.web3_utils import wei_to_xdai, xdai_to_wei
from tests_integration_with_local_chain.conftest import create_and_fund_random_account

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

    created_market = omen_create_market_tx(
        api_keys=test_keys,
        initial_funds=xdai_type(0.001),
        fee_perc=OMEN_DEFAULT_MARKET_FEE_PERC,
        question=question,
        closing_time=closing_time,
        category="cryptocurrency",
        language="en",
        outcomes=OMEN_BINARY_MARKET_OUTCOMES,
        auto_deposit=True,
        web3=local_web3,
    )
    logger.debug(f"Market created at address: {created_market.market_event}")
    # ToDo - Fix call here (subgraph will not update on localchain). Retrieve data directly from contract.
    market = omen_subgraph_handler.get_omen_market_by_market_id(
        created_market.market_event.fixed_product_market_maker_checksummed
    )

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
    responses = omen_subgraph_handler.get_responses(
        limit=None, question_id=market.question.id
    )
    assert len(responses) == 1, responses
    # ToDo: Once this test is fixed, check how to assert this, currently `answer` is HexBytes and OMEN_FALSE_OUTCOME is string, so it will never be equal.
    # assert answers[0].answer == OMEN_FALSE_OUTCOME, answers[0]

    # Note: We can not redeem the winning bet here, because the answer gets settled in 24 hours.
    # The same goes about claiming bonded xDai on Realitio.


def test_omen_create_market_wxdai(
    local_web3: Web3,
    test_keys: APIKeys,
) -> None:
    created_market = omen_create_market_tx(
        api_keys=test_keys,
        initial_funds=xdai_type(0.001),
        question="Will GNO hit $1000 in 2 minutes from creation of this market?",
        closing_time=utcnow() + timedelta(minutes=2),
        category="cryptocurrency",
        language="en",
        outcomes=OMEN_BINARY_MARKET_OUTCOMES,
        auto_deposit=True,
        web3=local_web3,
    )
    assert is_contract(
        local_web3, created_market.market_event.fixed_product_market_maker_checksummed
    )
    market_contract = OmenFixedProductMarketMakerContract(
        address=created_market.market_event.fixed_product_market_maker_checksummed
    )
    assert (
        market_contract.collateralToken(web3=local_web3)
        == WrappedxDaiContract().address
    )


def test_omen_create_market_sdai(
    local_web3: Web3,
    test_keys: APIKeys,
) -> None:
    created_market = omen_create_market_tx(
        api_keys=test_keys,
        initial_funds=xdai_type(100),
        question="Will GNO hit $1000 in 2 minutes from creation of this market?",
        closing_time=utcnow() + timedelta(minutes=2),
        category="cryptocurrency",
        language="en",
        outcomes=OMEN_BINARY_MARKET_OUTCOMES,
        auto_deposit=True,
        collateral_token_address=sDaiContract().address,
        web3=local_web3,
    )
    assert is_contract(
        local_web3, created_market.market_event.fixed_product_market_maker_checksummed
    )
    market_contract = OmenFixedProductMarketMakerContract(
        address=created_market.market_event.fixed_product_market_maker_checksummed
    )
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


@pytest.mark.parametrize(
    "collateral_token_address, expected_symbol",
    [
        (WrappedxDaiContract().address, "WXDAI"),
        (sDaiContract().address, "sDAI"),
    ],
)
def test_omen_fund_and_remove_fund_market(
    collateral_token_address: ChecksumAddress,
    expected_symbol: str,
    local_web3: Web3,
    test_keys: APIKeys,
) -> None:
    # You can double check your address at https://gnosisscan.io/ afterwards or at the market's address.
    market = OmenAgentMarket.from_data_model(
        OmenSubgraphHandler().get_omen_binary_markets_simple(
            limit=1,
            filter_by=FilterBy.OPEN,
            sort_by=SortBy.CLOSING_SOONEST,
            collateral_token_address_in=(collateral_token_address,),
        )[0]
    )
    collateral_token_contract = market.get_contract().get_collateral_token_contract(
        local_web3
    )
    assert (
        collateral_token_contract.symbol() == expected_symbol
    ), f"Should have retrieved {expected_symbol} market."
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
    outcome_str = get_bet_outcome(outcome)
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

    buy_id = market.place_bet(outcome=outcome, amount=bet_amount, web3=local_web3)

    # Check that we now have a position in the market.
    outcome_tokens = get_market_outcome_tokens()
    assert outcome_tokens.amount > 0

    sell_id = market.sell_tokens(
        outcome=outcome,
        amount=outcome_tokens,
        web3=local_web3,
        api_keys=api_keys,
    )

    # Check that we have sold our entire stake in the market.
    remaining_tokens = get_market_outcome_tokens()
    assert np.isclose(remaining_tokens.amount, 0, atol=1e-5)

    # Check that the IDs of buy and sell calls are valid transaction hashes
    buy_tx = local_web3.eth.get_transaction(HexStr(buy_id))
    sell_tx = local_web3.eth.get_transaction(HexStr(sell_id))
    for tx in [buy_tx, sell_tx]:
        assert tx is not None
        assert tx["from"] == api_keys.bet_from_address


def test_deposit_and_withdraw_wxdai(local_web3: Web3, test_keys: APIKeys) -> None:
    deposit_amount = xDai(10)
    fresh_account = create_and_fund_random_account(
        private_key=test_keys.bet_from_private_key,
        web3=local_web3,
        deposit_amount=xDai(deposit_amount * 2),  # 2* for safety
    )

    api_keys = APIKeys(
        BET_FROM_PRIVATE_KEY=private_key_type(fresh_account.key.hex()),
        SAFE_ADDRESS=None,
    )
    wxdai = WrappedxDaiContract()
    wxdai.deposit(
        api_keys=api_keys, amount_wei=xdai_to_wei(deposit_amount), web3=local_web3
    )
    balance = get_balances(address=fresh_account.address, web3=local_web3)
    assert balance.wxdai == deposit_amount

    wxdai.withdraw(
        api_keys=api_keys,
        amount_wei=xdai_to_wei(balance.wxdai),
        web3=local_web3,
    )

    balance = get_balances(address=fresh_account.address, web3=local_web3)
    assert balance.wxdai == xDai(0)


@pytest.mark.parametrize(
    "collateral_token_address, expected_symbol",
    [
        (WrappedxDaiContract().address, "WXDAI"),
        (sDaiContract().address, "sDAI"),
    ],
)
def test_place_bet_with_autodeposit(
    collateral_token_address: ChecksumAddress,
    expected_symbol: str,
    local_web3: Web3,
    test_keys: APIKeys,
) -> None:
    market = OmenAgentMarket.from_data_model(
        OmenSubgraphHandler().get_omen_binary_markets_simple(
            limit=1,
            filter_by=FilterBy.OPEN,
            sort_by=SortBy.CLOSING_SOONEST,
            collateral_token_address_in=(collateral_token_address,),
        )[0]
    )
    initial_balances = get_balances(address=test_keys.bet_from_address, web3=local_web3)
    collateral_token_contract = market.get_contract().get_collateral_token_contract(
        local_web3
    )
    assert (
        collateral_token_contract.symbol() == expected_symbol
    ), f"Should have retrieve {expected_symbol} market."
    assert isinstance(
        collateral_token_contract, ContractDepositableWrapperERC20OnGnosisChain
    ) or isinstance(
        collateral_token_contract, ContractERC4626OnGnosisChain
    ), "Omen market should adhere to one of these classes."

    # Start by moving all funds from wxdai to xdai
    if initial_balances.wxdai > 0:
        WrappedxDaiContract().withdraw(
            api_keys=test_keys,
            amount_wei=xdai_to_wei(initial_balances.wxdai),
            web3=local_web3,
        )

    # Check that we have xdai funds, but no wxdai funds
    initial_balances = get_balances(address=test_keys.bet_from_address, web3=local_web3)
    assert np.isclose(initial_balances.wxdai, xdai_type(0))
    assert initial_balances.xdai > xdai_type(0)

    # Try to place a bet with 90% of the xDai funds
    bet_amount = BetAmount(amount=initial_balances.xdai * 0.9, currency=Currency.xDai)
    market.place_bet(
        outcome=True,
        amount=bet_amount,
        omen_auto_deposit=True,
        web3=local_web3,
        api_keys=test_keys,
    )


def get_position_balance_by_position_id(
    from_address: ChecksumAddress, position_id: int, web3: Web3
) -> Wei:
    """Fetches balance from a given position in the ConditionalTokens contract."""
    return OmenConditionalTokenContract().balanceOf(
        from_address=from_address,
        position_id=position_id,
        web3=web3,
    )


@pytest.mark.parametrize(
    "ipfs_hash",
    ["0x3750ffa211dab39b4d0711eb27b02b56a17fa9d257ee549baa3110725fd1d41b", HASH_ZERO],
)
def test_add_predictions(local_web3: Web3, test_keys: APIKeys, ipfs_hash: str) -> None:
    agent_result_mapping = OmenAgentResultMappingContract()
    market_address = test_keys.public_key
    dummy_transaction_hash = (
        "0x3750ffa211dab39b4d0711eb27b02b56a17fa9d257ee549baa3110725fd1d41b"
    )
    stored_predictions = agent_result_mapping.get_predictions(
        market_address, web3=local_web3
    )
    p = ContractPrediction(
        tx_hashes=[HexBytes(dummy_transaction_hash)],
        estimated_probability_bps=5454,
        ipfs_hash=HexBytes(ipfs_hash),
        publisher=test_keys.public_key,
    )

    agent_result_mapping.add_prediction(test_keys, market_address, p, web3=local_web3)
    updated_stored_predictions = agent_result_mapping.get_predictions(
        market_address, web3=local_web3
    )
    assert len(updated_stored_predictions) == len(stored_predictions) + 1
    assert stored_predictions[-1] == p


def test_place_bet_with_prev_existing_positions(
    local_web3: Web3, test_keys: APIKeys
) -> None:
    # Fetch an open binary market.
    sh = OmenSubgraphHandler()
    market = sh.get_omen_binary_markets_simple(
        limit=1, filter_by=FilterBy.OPEN, sort_by=SortBy.CLOSING_SOONEST
    )[0]
    omen_agent_market = OmenAgentMarket.from_data_model(market)

    # Place a bet using a standard account (from .env)
    bet_amount = BetAmount(amount=1, currency=Currency.xDai)
    omen_agent_market.place_bet(True, bet_amount, web3=local_web3, api_keys=test_keys)

    conditional_token = OmenConditionalTokenContract()
    conditional_tokens_contract = local_web3.eth.contract(
        address=conditional_token.address, abi=conditional_token.abi
    )
    # We fetch the transfer single event emitted when outcome tokens were bought
    ls = conditional_tokens_contract.events.TransferSingle().get_logs()  # type: ignore[attr-defined]
    pos_id = ls[-1]["args"]["id"]
    # check position
    position_balance = get_position_balance_by_position_id(
        from_address=test_keys.bet_from_address, position_id=pos_id, web3=local_web3
    )
    # Assert that there is a positive balance since a bet was placed.
    assert position_balance > 0

    mock_positions = [
        Position(
            market_id=omen_agent_market.id,
            amounts={
                OutcomeStr(OMEN_TRUE_OUTCOME): TokenAmount(
                    amount=wei_to_xdai(Wei(position_balance)), currency=Currency.xDai
                )
            },
        )
    ]

    # We patch get_positions since the function logic uses the subgraph.
    with patch(
        "prediction_market_agent_tooling.markets.omen.omen.OmenAgentMarket.get_positions",
        return_value=mock_positions,
    ):
        # We now want to sell the recently opened position.
        omen_agent_market.liquidate_existing_positions(
            False, web3=local_web3, api_keys=test_keys
        )

    position_balance_after_sell = get_position_balance_by_position_id(
        from_address=test_keys.bet_from_address, position_id=pos_id, web3=local_web3
    )

    # We assert that positions were liquidated if < 1% of the original outcome tokens bought remain
    # in the position. This is because of implementation details in the ConditionalTokens contract,
    # avoiding the position to be fully sold.
    assert position_balance_after_sell < 0.01 * position_balance  # xDAI
