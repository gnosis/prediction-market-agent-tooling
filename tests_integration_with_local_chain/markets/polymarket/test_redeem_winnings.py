from datetime import datetime
from unittest import mock

from ape import Contract
from ape import accounts as AccountManagerApe
from web3 import Web3

from prediction_market_agent_tooling.config import APIKeys
from prediction_market_agent_tooling.gtypes import (
    OutcomeWei,
    Wei,
    private_key_type,
    xDai,
)
from prediction_market_agent_tooling.markets.polymarket.api import (
    get_polymarkets_with_pagination,
)
from prediction_market_agent_tooling.markets.polymarket.data_models import (
    PolymarketGammaMarket,
)
from prediction_market_agent_tooling.markets.polymarket.polymarket import (
    PolymarketAgentMarket,
)
from prediction_market_agent_tooling.markets.polymarket.polymarket_contracts import (
    PolymarketConditionalTokenContract,
    USDCeContract,
)
from prediction_market_agent_tooling.markets.polymarket.polymarket_subgraph_handler import (
    MarketPosition,
    PolymarketSubgraphHandler,
)
from prediction_market_agent_tooling.tools.cow.cow_order import handle_allowance
from prediction_market_agent_tooling.tools.utils import check_not_none
from tests_integration_with_local_chain.conftest import create_and_fund_random_account


def build_mock_market(
    market: PolymarketGammaMarket, subgraph_handler: PolymarketSubgraphHandler
) -> MarketPosition:
    condition = subgraph_handler.get_conditions(condition_ids=[market.conditionId])[0]

    mock_condition = mock.MagicMock()
    mock_condition.id = market.conditionId
    mock_condition.payoutNumerators = condition.payoutNumerators
    mock_condition.outcomeSlotCount = condition.outcomeSlotCount
    mock_condition.resolutionTimestamp = int(datetime.now().timestamp())
    mock_condition.index_sets = [i + 1 for i in range(condition.outcomeSlotCount)]

    mock_market = mock.MagicMock()
    mock_market.condition = mock_condition

    mock_position = mock.MagicMock(wraps=MarketPosition)
    mock_position.market = mock_market
    return mock_position


def test_redeem(
    polygon_local_web3: Web3,
    polymarket_subgraph_handler_test: PolymarketSubgraphHandler,
) -> None:
    markets = check_not_none(
        get_polymarkets_with_pagination(closed=True, limit=1, only_binary=True)
    )
    market = check_not_none(markets[0].markets)[0]
    # should exist since filtered by this on the api client call

    amount_wei = Wei(int(1 * 1e6))
    fresh_account = create_and_fund_random_account(
        web3=polygon_local_web3,
        deposit_amount=xDai(amount_wei.value * 2),  # 2* for safety
    )

    api_keys = APIKeys(
        BET_FROM_PRIVATE_KEY=private_key_type(fresh_account.key.hex()),
        SAFE_ADDRESS=None,
    )

    # we impersonate a whale account (Wormhole token bridge) to fetch some USDC
    whale_account = Web3.to_checksum_address(
        "0x5a58505a96D1dbf8dF91cB21B54419FC36e93fdE"
    )
    with AccountManagerApe.use_sender(whale_account):
        contract_instance = USDCeContract()
        contract = Contract(
            address=contract_instance.address, abi=contract_instance.abi
        )
        receipt = contract.transfer(api_keys.bet_from_address, amount_wei.value)
        print(receipt)

    condition_id = market.conditionId
    c = PolymarketConditionalTokenContract()

    # allowance
    handle_allowance(
        api_keys=api_keys,
        sell_token=USDCeContract().address,
        amount_to_check_wei=amount_wei,
        for_address=c.address,
        web3=polygon_local_web3,
    )

    c.splitPosition(
        api_keys=api_keys,
        collateral_token=USDCeContract().address,
        condition_id=condition_id,
        outcome_slot_count=len(market.outcomes_list),
        amount_wei=amount_wei,
        web3=polygon_local_web3,
    )
    mock_position = build_mock_market(market, polymarket_subgraph_handler_test)
    with mock.patch(
        "prediction_market_agent_tooling.markets.polymarket.polymarket_subgraph_handler.PolymarketSubgraphHandler.get_market_positions_from_user",
        return_value=[mock_position],
    ):
        PolymarketAgentMarket.redeem_winnings(
            api_keys=api_keys, web3=polygon_local_web3
        )

    # we assert that the outcome tokens with positive payouts were transferred out of the account
    ctf = PolymarketConditionalTokenContract()
    for token_id in market.token_ids:
        user_balance = ctf.balanceOf(
            from_address=api_keys.bet_from_address,
            position_id=token_id,
            web3=polygon_local_web3,
        )
        assert user_balance == OutcomeWei.zero()
