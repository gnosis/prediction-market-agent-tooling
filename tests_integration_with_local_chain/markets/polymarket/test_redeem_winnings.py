from ape import accounts as AccountManagerApe, Contract
from web3 import Web3

from prediction_market_agent_tooling.config import APIKeys
from prediction_market_agent_tooling.gtypes import (
    Wei,
    OutcomeWei,
)
from prediction_market_agent_tooling.markets.polymarket.api import (
    get_polymarkets_with_pagination,
)
from prediction_market_agent_tooling.markets.polymarket.polymarket import (
    PolymarketAgentMarket,
)
from prediction_market_agent_tooling.markets.polymarket.polymarket_contracts import (
    PolymarketConditionalTokenContract,
    USDCeContract,
)
from prediction_market_agent_tooling.tools.utils import check_not_none


def test_redeem(test_keys: APIKeys, polygon_local_web3: Web3) -> None:
    markets = get_polymarkets_with_pagination(closed=True, limit=1)
    market = check_not_none(
        markets[0].markets[0]
    )  # should exist since filtered by this on the api client call

    keys = APIKeys()
    amount_wei = Wei(1 * 1e6)

    # we impersonate a whale account (Wormhole token bridge) to fetch some USDC
    whale_account = Web3.to_checksum_address(
        "0x5a58505a96D1dbf8dF91cB21B54419FC36e93fdE"
    )
    with AccountManagerApe.use_sender(whale_account):
        contract_instance = USDCeContract()
        contract = Contract(address=contract_instance, abi=contract_instance.abi)
        receipt = contract.transferFrom(
            sender=whale_account, to=keys.bet_from_address, amount=amount_wei
        )
        print(receipt)

    condition_id = market.condition_id
    c = PolymarketConditionalTokenContract()
    c.splitPosition(
        api_keys=keys,
        collateral_token=USDCeContract().address,
        condition_id=condition_id,
        outcome_slot_count=len(market.outcomes_list),
        amount_wei=amount_wei,
        web3=polygon_local_web3,
    )

    PolymarketAgentMarket.redeem_winnings(api_keys=keys, web3=polygon_local_web3)

    # we assert that the outcome tokens with positive payouts were transferred out of the account
    ctf = PolymarketConditionalTokenContract()
    for token_id in market.token_ids:
        user_balance = ctf.balanceOf(
            from_address=keys.bet_from_address,
            position_id=token_id,
            web3=polygon_local_web3,
        )
        assert user_balance == OutcomeWei.zero()
