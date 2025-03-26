import time
from datetime import timedelta
from unittest.mock import patch

import pytest
from web3 import Web3
from web3.constants import HASH_ZERO

from prediction_market_agent_tooling.config import APIKeys
from prediction_market_agent_tooling.gtypes import (
    USD,
    ChecksumAddress,
    CollateralToken,
    HexAddress,
    HexStr,
    OutcomeToken,
    OutcomeWei,
    private_key_type,
    xDai,
)
from prediction_market_agent_tooling.loggers import logger
from prediction_market_agent_tooling.markets.agent_market import FilterBy, SortBy
from prediction_market_agent_tooling.markets.data_models import ExistingPosition
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
from prediction_market_agent_tooling.tools.tokens.usd import (
    get_token_in_usd,
    get_xdai_in_usd,
)
from prediction_market_agent_tooling.tools.utils import utcnow
from tests_integration_with_local_chain.conftest import create_and_fund_random_account

DEFAULT_REASON = "Test logic need to be rewritten for usage of local chain, see ToDos"


def is_contract(web3: Web3, contract_address: ChecksumAddress) -> bool:
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
        initial_funds=USD(0.001),
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
        amount=USD(0.001),
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
        bond=xDai(0.001).as_xdai_wei,
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
        initial_funds=USD(0.001),
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
        initial_funds=USD(100),
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
    balance_yes = market.get_token_balance(
        user_id=user_address,
        outcome=OMEN_TRUE_OUTCOME,
    )
    assert float(balance_yes) == 0

    balance_no = market.get_token_balance(
        user_id=user_address,
        outcome=OMEN_FALSE_OUTCOME,
    )
    assert float(balance_no) == 0


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
            sort_by=SortBy.NEWEST,
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

    funds = xDai(0.1)
    remove_fund = xDai(0.01).as_xdai_wei

    omen_fund_market_tx(
        api_keys=test_keys,
        market=market,
        funds=get_xdai_in_usd(funds),
        auto_deposit=True,
        web3=local_web3,
    )

    omen_remove_fund_market_tx(
        api_keys=test_keys,
        market=market,
        shares=remove_fund.as_wei,
        web3=local_web3,
    )


@pytest.mark.parametrize(
    "collateral_token_address",
    [
        WrappedxDaiContract().address,
        sDaiContract().address,
    ],
)
def test_omen_buy_and_sell_outcome(
    collateral_token_address: ChecksumAddress,
    local_web3: Web3,
    test_keys: APIKeys,
) -> None:
    # Tests both buying and selling, so we are back at the square one in the wallet (minues fees).
    # You can double check your address at https://gnosisscan.io/ afterwards.
    market = OmenAgentMarket.from_data_model(
        pick_binary_market(collateral_token_address_in=(collateral_token_address,))
    )
    print(market.url)
    outcome = True
    outcome_str = get_bet_outcome(outcome)
    bet_amount = USD(0.4)

    def get_market_outcome_tokens() -> OutcomeToken:
        return market.get_token_balance(
            user_id=test_keys.bet_from_address,
            outcome=outcome_str,
            web3=local_web3,
        )

    # Check our wallet has sufficient funds
    balances = get_balances(address=test_keys.bet_from_address, web3=local_web3)
    assert balances.xdai.value > bet_amount.value

    buy_id = market.place_bet(
        outcome=outcome,
        amount=bet_amount,
        web3=local_web3,
        api_keys=test_keys,
    )

    # Check that we now have a position in the market.
    outcome_tokens = get_market_outcome_tokens()
    assert get_market_outcome_tokens() > 0

    sell_id = market.sell_tokens(
        outcome=outcome,
        amount=outcome_tokens,
        web3=local_web3,
        api_keys=test_keys,
    )

    # Check that we have sold our entire stake in the market up to some slippage
    remaining_tokens = get_market_outcome_tokens()
    assert remaining_tokens.value < outcome_tokens.value * 0.01

    # Check that the IDs of buy and sell calls are valid transaction hashes
    buy_tx = local_web3.eth.get_transaction(HexStr(buy_id))
    sell_tx = local_web3.eth.get_transaction(HexStr(sell_id))
    for tx in [buy_tx, sell_tx]:
        assert tx is not None
        assert tx["from"] == test_keys.bet_from_address


def test_deposit_and_withdraw_wxdai(local_web3: Web3, test_keys: APIKeys) -> None:
    deposit_amount = xDai(10)
    fresh_account = create_and_fund_random_account(
        private_key=test_keys.bet_from_private_key,
        web3=local_web3,
        deposit_amount=xDai(deposit_amount.value * 2),  # 2* for safety
    )

    api_keys = APIKeys(
        BET_FROM_PRIVATE_KEY=private_key_type(fresh_account.key.hex()),
        SAFE_ADDRESS=None,
    )
    wxdai = WrappedxDaiContract()
    wxdai.deposit(
        api_keys=api_keys,
        amount_wei=deposit_amount.as_xdai_wei.as_wei,
        web3=local_web3,
    )
    balance = get_balances(address=fresh_account.address, web3=local_web3)
    assert balance.wxdai.value == deposit_amount.value

    wxdai.withdraw(
        api_keys=api_keys,
        amount_wei=balance.wxdai.as_wei,
        web3=local_web3,
    )

    balance = get_balances(address=fresh_account.address, web3=local_web3)
    assert balance.wxdai == CollateralToken(0)


@pytest.mark.parametrize(
    "collateral_token_address, expected_symbol",
    [
        # Test only wxDai and sDai there, because for anything else we would need CoW which isn't available on local chain.
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
            sort_by=SortBy.NEWEST,
            collateral_token_address_in=(collateral_token_address,),
        )[0]
    )
    print(market.url)
    collateral_token_contract = market.get_contract().get_collateral_token_contract(
        local_web3
    )
    assert (
        collateral_token_contract.symbol(local_web3) == expected_symbol
    ), f"Should have retrieve {expected_symbol} market."
    assert isinstance(
        collateral_token_contract, ContractDepositableWrapperERC20OnGnosisChain
    ) or isinstance(
        collateral_token_contract, ContractERC4626OnGnosisChain
    ), "Omen market should adhere to one of these classes."

    # If we have anything in the collateral token, withdraw it.
    if (
        balance_in_collateral := collateral_token_contract.balance_of_in_tokens(
            for_address=test_keys.bet_from_address, web3=local_web3
        )
    ) > 0:
        balance_in_collateral *= 0.95  # Withdraw only most of it.
        if isinstance(
            collateral_token_contract, ContractDepositableWrapperERC20OnGnosisChain
        ):
            collateral_token_contract.withdraw(
                api_keys=test_keys,
                amount_wei=balance_in_collateral.as_wei,
                web3=local_web3,
            )
        elif isinstance(collateral_token_contract, ContractERC4626OnGnosisChain):
            collateral_token_contract.withdraw_in_shares(
                api_keys=test_keys,
                shares_wei=balance_in_collateral.as_wei,
                web3=local_web3,
            )
        else:
            raise ValueError("Unknown contract type for this test.")

    # Try to place a bet with 10% of the xDai funds (xDai ~= USD)
    balances = get_balances(address=test_keys.bet_from_address, web3=local_web3)
    bet_amount = get_xdai_in_usd(balances.xdai * 0.1)

    # Check that we don't have enough in the collateral token
    assert (
        get_token_in_usd(
            collateral_token_contract.balance_of_in_tokens(
                for_address=test_keys.bet_from_address, web3=local_web3
            ),
            collateral_token_contract.address,
        )
        < bet_amount
    )

    market.place_bet(
        outcome=True,
        amount=bet_amount,
        auto_deposit=True,
        web3=local_web3,
        api_keys=test_keys,
    )


def get_position_balance_by_position_id(
    from_address: ChecksumAddress, position_id: int, web3: Web3
) -> OutcomeWei:
    """Fetches balance from a given position in the ConditionalTokens contract."""
    return OmenConditionalTokenContract().balanceOf(
        from_address=from_address,
        position_id=position_id,
        web3=web3,
    )


@pytest.mark.parametrize(
    "ipfs_hash",
    [
        "0x3750ffa211dab39b4d0711eb27b02b56a17fa9d257ee549baa3110725fd1d41b",  # web3-private-key-ok
        HASH_ZERO,
    ],
)
def test_add_predictions(local_web3: Web3, test_keys: APIKeys, ipfs_hash: str) -> None:
    agent_result_mapping = OmenAgentResultMappingContract()
    market_address = test_keys.bet_from_address
    dummy_transaction_hash = "0x3750ffa211dab39b4d0711eb27b02b56a17fa9d257ee549baa3110725fd1d41b"  # web3-private-key-ok
    stored_predictions = agent_result_mapping.get_predictions(
        market_address, web3=local_web3
    )
    p = ContractPrediction(
        tx_hashes=[HexBytes(dummy_transaction_hash)],
        estimated_probability_bps=5454,
        ipfs_hash=HexBytes(ipfs_hash),
        publisher=test_keys.bet_from_address,
    )

    agent_result_mapping.add_prediction(test_keys, market_address, p, web3=local_web3)
    updated_stored_predictions = agent_result_mapping.get_predictions(
        market_address, web3=local_web3
    )
    assert len(updated_stored_predictions) == len(stored_predictions) + 1
    assert updated_stored_predictions[-1] == p


def test_place_bet_with_prev_existing_positions(
    local_web3: Web3, test_keys: APIKeys
) -> None:
    # Fetch an open binary market.
    sh = OmenSubgraphHandler()
    market = sh.get_omen_binary_markets_simple(
        limit=1, filter_by=FilterBy.OPEN, sort_by=SortBy.NEWEST
    )[0]
    omen_agent_market = OmenAgentMarket.from_data_model(market)

    # Place a bet using a standard account (from .env)
    bet_amount = USD(1)
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
    assert position_balance.value > 0
    mock_positions = [
        ExistingPosition(
            market_id=omen_agent_market.id,
            amounts_current={
                OMEN_TRUE_OUTCOME: omen_agent_market.get_token_in_usd(
                    omen_agent_market.get_sell_value_of_outcome_token(
                        OMEN_TRUE_OUTCOME, position_balance.as_outcome_token, local_web3
                    )
                )
            },
            amounts_potential={
                OMEN_TRUE_OUTCOME: omen_agent_market.get_token_in_usd(
                    position_balance.as_outcome_token.as_token
                )
            },
            amounts_ot={OMEN_TRUE_OUTCOME: position_balance.as_outcome_token},
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
    assert position_balance_after_sell.value < 0.01 * position_balance.value
