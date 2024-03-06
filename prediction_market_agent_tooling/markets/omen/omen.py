import typing as t
from datetime import datetime
from decimal import Decimal

from prediction_market_agent_tooling.config import APIKeys
from prediction_market_agent_tooling.gtypes import ChecksumAddress, PrivateKey, xDai
from prediction_market_agent_tooling.markets.agent_market import AgentMarket
from prediction_market_agent_tooling.markets.data_models import BetAmount, Currency
from prediction_market_agent_tooling.markets.omen.data_models import (
    OMEN_FALSE_OUTCOME,
    OMEN_TRUE_OUTCOME,
    OmenBet,
    OmenMarket,
)
from prediction_market_agent_tooling.tools.utils import utcnow

"""
Python API for Omen prediction market.

Their API is available as graph on https://thegraph.com/explorer/subgraphs/9V1aHHwkK4uPWgBH6ZLzwqFEkoHTHPS7XHKyjZWe8tEf?view=Overview&chain=mainnet,
but to not use our own credits, seems we can use their api deployment directly: https://api.thegraph.com/subgraphs/name/protofire/omen-xdai/graphql (link to the online playground)
"""


class OmenAgentMarket(AgentMarket):
    """
    Omen's market class that can be used by agents to make predictions.
    """

    currency: t.ClassVar[Currency] = Currency.xDai
    collateral_token_contract_address_checksummed: ChecksumAddress
    market_maker_contract_address_checksummed: ChecksumAddress

    def get_tiny_bet_amount(self) -> BetAmount:
        return BetAmount(amount=Decimal(0.00001), currency=self.currency)

    def place_bet(
        self, outcome: bool, amount: BetAmount, omen_auto_deposit: bool = True
    ) -> None:
        if amount.currency != self.currency:
            raise ValueError(f"Omen bets are made in xDai. Got {amount.currency}.")
        amount_xdai = xDai(amount.amount)
        keys = APIKeys()
        binary_omen_buy_outcome_tx(
            amount=amount_xdai,
            from_address=keys.bet_from_address,
            from_private_key=keys.bet_from_private_key,
            market=self,
            binary_outcome=outcome,
            auto_deposit=omen_auto_deposit,
        )

    @staticmethod
    def from_data_model(model: OmenMarket) -> "OmenAgentMarket":
        return OmenAgentMarket(
            id=model.id,
            question=model.title,
            outcomes=model.outcomes,
            collateral_token_contract_address_checksummed=model.collateral_token_contract_address_checksummed,
            market_maker_contract_address_checksummed=model.market_maker_contract_address_checksummed,
            p_yes=model.p_yes,
        )

    @staticmethod
    def get_binary_markets(limit: int) -> list[AgentMarket]:
        return [
            OmenAgentMarket.from_data_model(m)
            for m in get_omen_binary_markets(limit=limit)
        ]


import json
import os
import random
import typing as t
from datetime import datetime
from enum import Enum

import requests
from web3 import Web3
from web3.types import TxParams, TxReceipt

from prediction_market_agent_tooling.gtypes import (
    ABI,
    ChecksumAddress,
    HexAddress,
    HexBytes,
    OmenOutcomeToken,
    PrivateKey,
    Wei,
    xDai,
)
from prediction_market_agent_tooling.markets.omen.data_models import OmenMarket
from prediction_market_agent_tooling.tools.gnosis_rpc import GNOSIS_RPC_URL
from prediction_market_agent_tooling.tools.web3_utils import (
    WXDAI_ABI,
    WXDAI_CONTRACT_ADDRESS,
    add_fraction,
    call_function_on_contract,
    call_function_on_contract_tx,
    remove_fraction,
    xdai_to_wei,
    xdai_type,
)

OMEN_QUERY_BATCH_SIZE = 1000
OMEN_DEFAULT_MARKET_FEE = 0.02  # 2% fee from the buying shares amount.
DEFAULT_COLLATERAL_TOKEN_CONTRACT_ADDRESS = WXDAI_CONTRACT_ADDRESS


class Arbitrator(str, Enum):
    KLEROS = "kleros"
    DXDAO = "dxdao"


with open(
    os.path.join(
        os.path.dirname(os.path.realpath(__file__)), "../../abis/omen_fpmm.abi.json"
    )
) as f:
    # File content taken from https://github.com/protofire/omen-exchange/blob/master/app/src/abi/marketMaker.json.
    # Factory contract at https://gnosisscan.io/address/0x9083a2b699c0a4ad06f63580bde2635d26a3eef0.
    OMEN_FPMM_ABI = ABI(f.read())
    # This doesn't have a fixed contract address, as this is something created by the factory below.

with open(
    os.path.join(
        os.path.dirname(os.path.realpath(__file__)),
        "../../abis/omen_fpmm_factory.abi.json",
    )
) as f:
    # Contract ABI taken from https://gnosisscan.io/address/0x9083A2B699c0a4AD06F63580BDE2635d26a3eeF0#code.
    OMEN_FPMM_FACTORY_ABI = ABI(f.read())
    OMEN_FPMM_FACTORY_CONTRACT_ADDRESS: ChecksumAddress = Web3.to_checksum_address(
        "0x9083A2B699c0a4AD06F63580BDE2635d26a3eeF0"
    )

with open(
    os.path.join(
        os.path.dirname(os.path.realpath(__file__)),
        "../../abis/omen_fpmm_conditionaltokens.abi.json",
    )
) as f:
    # Contract ABI taken from https://gnosisscan.io/address/0xCeAfDD6bc0bEF976fdCd1112955828E00543c0Ce#code.
    OMEN_FPMM_CONDITIONALTOKENS_ABI = ABI(f.read())
    OMEN_FPMM_CONDITIONALTOKENS_CONTRACT_ADDRESS: ChecksumAddress = (
        Web3.to_checksum_address("0xCeAfDD6bc0bEF976fdCd1112955828E00543c0Ce")
    )

with open(
    os.path.join(
        os.path.dirname(os.path.realpath(__file__)),
        "../../abis/omen_realitio.abi.json",
    )
) as f:
    # Contract ABI taken from https://gnosisscan.io/address/0x79e32aE03fb27B07C89c0c568F80287C01ca2E57#code.
    OMEN_REALITIO_ABI = ABI(f.read())
    OMEN_REALITIO_CONTRACT_ADDRESS: ChecksumAddress = Web3.to_checksum_address(
        "0x79e32aE03fb27B07C89c0c568F80287C01ca2E57"
    )

with open(
    os.path.join(
        os.path.dirname(os.path.realpath(__file__)),
        "../../abis/omen_oracle.abi.json",
    )
) as f:
    # Contract ABI taken from https://gnosisscan.io/address/0xAB16D643bA051C11962DA645f74632d3130c81E2#code.
    OMEN_ORACLE_ABI = ABI(f.read())
    OMEN_ORACLE_CONTRACT_ADDRESS: ChecksumAddress = Web3.to_checksum_address(
        "0xAB16D643bA051C11962DA645f74632d3130c81E2"
    )

with open(
    os.path.join(
        os.path.dirname(os.path.realpath(__file__)),
        "../../abis/omen_kleros.abi.json",
    )
) as f:
    # Contract ABI taken from https://gnosisscan.io/address/0xe40DD83a262da3f56976038F1554Fe541Fa75ecd#code.
    OMEN_KLEROS_ABI = ABI(f.read())
    OMEN_KLEROS_CONTRACT_ADDRESS: ChecksumAddress = Web3.to_checksum_address(
        "0xe40DD83a262da3f56976038F1554Fe541Fa75ecd"
    )

with open(
    os.path.join(
        os.path.dirname(os.path.realpath(__file__)),
        "../../abis/omen_dxdao.abi.json",
    )
) as f:
    # Contract ABI taken from https://gnosisscan.io/address/0xFe14059344b74043Af518d12931600C0f52dF7c5#code.
    OMEN_DXDAO_ABI = ABI(f.read())
    OMEN_DXDAO_CONTRACT_ADDRESS: ChecksumAddress = Web3.to_checksum_address(
        "0xFe14059344b74043Af518d12931600C0f52dF7c5"
    )


THEGRAPH_QUERY_URL = "https://api.thegraph.com/subgraphs/name/protofire/omen-xdai"

_QUERY_GET_SINGLE_FIXED_PRODUCT_MARKET_MAKER = """
query getFixedProductMarketMaker($id: String!) {
    fixedProductMarketMaker(
        id: $id
    ) {
        id
        title
        category
        creationTimestamp
        collateralVolume
        usdVolume
        collateralToken
        outcomes
        outcomeTokenAmounts
        outcomeTokenMarginalPrices
        fee
    }
}
"""


def construct_query_get_fixed_product_markets_makers(include_creator: bool) -> str:
    query = """query getFixedProductMarketMakers($first: Int!, $outcomes: [String!], $creator: Bytes = null) {
        fixedProductMarketMakers(
            where: {
                creator: $creator,
                isPendingArbitration: false,
                outcomes: $outcomes
            },
            orderBy: creationTimestamp,
            orderDirection: desc,
            first: $first
        ) {
            id
            title
            category
            creationTimestamp
            collateralVolume
            usdVolume
            collateralToken
            outcomes
            outcomeTokenAmounts
            outcomeTokenMarginalPrices
            fee
        }
    }"""

    if not include_creator:
        # If we aren't filtering by query, we need to remove it from where, otherwise "creator: null" will return 0 results.
        query = query.replace("creator: $creator,", "")

    return query


def get_arbitrator_contract_address_and_abi(
    arbitrator: Arbitrator,
) -> tuple[ChecksumAddress, ABI]:
    if arbitrator == Arbitrator.KLEROS:
        return OMEN_KLEROS_CONTRACT_ADDRESS, OMEN_KLEROS_ABI
    if arbitrator == Arbitrator.DXDAO:
        return OMEN_DXDAO_CONTRACT_ADDRESS, OMEN_DXDAO_ABI
    raise ValueError(f"Unknown arbitrator: {arbitrator}")


def get_omen_markets(
    first: int, outcomes: list[str], creator: HexAddress | None = None
) -> list[OmenMarket]:
    markets = requests.post(
        THEGRAPH_QUERY_URL,
        json={
            "query": construct_query_get_fixed_product_markets_makers(
                include_creator=creator is not None
            ),
            "variables": {
                "first": first,
                "outcomes": outcomes,
                "creator": creator,
            },
        },
        headers={"Content-Type": "application/json"},
    ).json()["data"]["fixedProductMarketMakers"]
    return [OmenMarket.model_validate(market) for market in markets]


def get_omen_binary_markets(
    limit: int, creator: HexAddress | None = None
) -> list[OmenMarket]:
    return get_omen_markets(
        limit, [OMEN_TRUE_OUTCOME, OMEN_FALSE_OUTCOME], creator=creator
    )


def pick_binary_market() -> OmenMarket:
    return get_omen_binary_markets(limit=1)[0]


def get_market(market_id: str) -> OmenMarket:
    market = requests.post(
        THEGRAPH_QUERY_URL,
        json={
            "query": _QUERY_GET_SINGLE_FIXED_PRODUCT_MARKET_MAKER,
            "variables": {
                "id": market_id,
            },
        },
        headers={"Content-Type": "application/json"},
    ).json()["data"]["fixedProductMarketMaker"]
    return OmenMarket.model_validate(market)


def omen_approve_market_maker_to_spend_collateral_token_tx(
    web3: Web3,
    market_maker_contract_address: ChecksumAddress,
    collateral_token_contract_address: ChecksumAddress,
    amount_wei: Wei,
    from_address: ChecksumAddress,
    from_private_key: PrivateKey,
    tx_params: t.Optional[TxParams] = None,
) -> TxReceipt:
    return call_function_on_contract_tx(
        web3=web3,
        contract_address=collateral_token_contract_address,
        contract_abi=WXDAI_ABI,
        from_address=from_address,
        from_private_key=from_private_key,
        function_name="approve",
        function_params=[
            market_maker_contract_address,
            amount_wei,
        ],
        tx_params=tx_params,
    )


def omen_approve_all_market_maker_to_move_conditionaltokens_tx(
    web3: Web3,
    market: OmenAgentMarket,
    approve: bool,
    from_address: ChecksumAddress,
    from_private_key: PrivateKey,
    tx_params: t.Optional[TxParams] = None,
) -> TxReceipt:
    # Get the address of conditional token's of this market.
    conditionaltokens_address = omen_get_market_maker_conditionaltokens_address(
        web3, market
    )
    return call_function_on_contract_tx(
        web3=web3,
        contract_address=Web3.to_checksum_address(conditionaltokens_address),
        contract_abi=OMEN_FPMM_CONDITIONALTOKENS_ABI,
        from_address=from_address,
        from_private_key=from_private_key,
        function_name="setApprovalForAll",
        function_params=[
            market.market_maker_contract_address_checksummed,
            approve,
        ],
        tx_params=tx_params,
    )


def omen_get_balance_of_erc20_token(
    web3: Web3,
    contract_address: ChecksumAddress,
    for_address: ChecksumAddress,
) -> Wei:
    balance: Wei = call_function_on_contract(
        web3=web3,
        contract_address=contract_address,
        contract_abi=WXDAI_ABI,
        function_name="balanceOf",
        function_params=[for_address],
    )
    return balance


def omen_deposit_collateral_token_tx(
    web3: Web3,
    collateral_token_contract_address: ChecksumAddress,
    amount_wei: Wei,
    from_address: ChecksumAddress,
    from_private_key: PrivateKey,
    tx_params: t.Optional[TxParams] = None,
) -> TxReceipt:
    return call_function_on_contract_tx(
        web3=web3,
        contract_address=collateral_token_contract_address,
        contract_abi=WXDAI_ABI,
        from_address=from_address,
        from_private_key=from_private_key,
        function_name="deposit",
        tx_params={"value": amount_wei, **(tx_params or {})},
    )


def omen_withdraw_collateral_token_tx(
    web3: Web3,
    market: OmenAgentMarket,
    amount_wei: Wei,
    from_address: ChecksumAddress,
    from_private_key: PrivateKey,
    tx_params: t.Optional[TxParams] = None,
) -> TxReceipt:
    return call_function_on_contract_tx(
        web3=web3,
        contract_address=market.collateral_token_contract_address_checksummed,
        contract_abi=WXDAI_ABI,
        from_address=from_address,
        from_private_key=from_private_key,
        function_name="withdraw",
        function_params=[amount_wei],
        tx_params=tx_params or {},
    )


def omen_calculate_buy_amount(
    web3: Web3,
    market: OmenAgentMarket,
    investment_amount: Wei,
    outcome_index: int,
) -> OmenOutcomeToken:
    """
    Returns amount of shares we will get for the given outcome_index for the given investment amount.
    """
    calculated_shares: OmenOutcomeToken = call_function_on_contract(
        web3,
        market.market_maker_contract_address_checksummed,
        OMEN_FPMM_ABI,
        "calcBuyAmount",
        [investment_amount, outcome_index],
    )
    return calculated_shares


def omen_calculate_sell_amount(
    web3: Web3,
    market: OmenAgentMarket,
    return_amount: Wei,
    outcome_index: int,
) -> OmenOutcomeToken:
    """
    Returns amount of shares we will sell for the requested wei.
    """
    calculated_shares: OmenOutcomeToken = call_function_on_contract(
        web3,
        market.market_maker_contract_address_checksummed,
        OMEN_FPMM_ABI,
        "calcSellAmount",
        [return_amount, outcome_index],
    )
    return calculated_shares


def omen_get_market_maker_conditionaltokens_address(
    web3: Web3,
    market: OmenAgentMarket,
) -> HexAddress:
    address: HexAddress = call_function_on_contract(
        web3,
        market.market_maker_contract_address_checksummed,
        OMEN_FPMM_ABI,
        "conditionalTokens",
    )
    return address


def omen_buy_shares_tx(
    web3: Web3,
    market: OmenAgentMarket,
    amount_wei: Wei,
    outcome_index: int,
    min_outcome_tokens_to_buy: OmenOutcomeToken,
    from_address: ChecksumAddress,
    from_private_key: PrivateKey,
    tx_params: t.Optional[TxParams] = None,
) -> TxReceipt:
    return call_function_on_contract_tx(
        web3=web3,
        contract_address=market.market_maker_contract_address_checksummed,
        contract_abi=OMEN_FPMM_ABI,
        from_address=from_address,
        from_private_key=from_private_key,
        function_name="buy",
        function_params=[
            amount_wei,
            outcome_index,
            min_outcome_tokens_to_buy,
        ],
        tx_params=tx_params,
    )


def omen_sell_shares_tx(
    web3: Web3,
    market: OmenAgentMarket,
    amount_wei: Wei,
    outcome_index: int,
    max_outcome_tokens_to_sell: OmenOutcomeToken,
    from_address: ChecksumAddress,
    from_private_key: PrivateKey,
    tx_params: t.Optional[TxParams] = None,
) -> TxReceipt:
    return call_function_on_contract_tx(
        web3=web3,
        contract_address=market.market_maker_contract_address_checksummed,
        contract_abi=OMEN_FPMM_ABI,
        from_address=from_address,
        from_private_key=from_private_key,
        function_name="sell",
        function_params=[
            amount_wei,
            outcome_index,
            max_outcome_tokens_to_sell,
        ],
        tx_params=tx_params,
    )


def omen_buy_outcome_tx(
    amount: xDai,
    from_address: ChecksumAddress,
    from_private_key: PrivateKey,
    market: OmenAgentMarket,
    outcome: str,
    auto_deposit: bool,
) -> None:
    """
    Bets the given amount of xDai for the given outcome in the given market.
    """
    web3 = Web3(Web3.HTTPProvider(GNOSIS_RPC_URL))
    amount_wei = xdai_to_wei(amount)
    from_address_checksummed = Web3.to_checksum_address(from_address)

    # Get the index of the outcome we want to buy.
    outcome_index: int = market.get_outcome_index(outcome)

    # Calculate the amount of shares we will get for the given investment amount.
    expected_shares = omen_calculate_buy_amount(web3, market, amount_wei, outcome_index)
    # Allow 1% slippage.
    expected_shares = remove_fraction(expected_shares, 0.01)
    # Approve the market maker to withdraw our collateral token.
    omen_approve_market_maker_to_spend_collateral_token_tx(
        web3=web3,
        market_maker_contract_address=market.market_maker_contract_address_checksummed,
        collateral_token_contract_address=market.collateral_token_contract_address_checksummed,
        amount_wei=amount_wei,
        from_address=from_address_checksummed,
        from_private_key=from_private_key,
    )
    # Deposit xDai to the collateral token,
    # this can be skipped, if we know we already have enough collateral tokens.
    collateral_token_balance = omen_get_balance_of_erc20_token(
        web3=web3,
        contract_address=market.collateral_token_contract_address_checksummed,
        for_address=from_address_checksummed,
    )
    if auto_deposit and collateral_token_balance < amount_wei:
        omen_deposit_collateral_token_tx(
            web3=web3,
            collateral_token_contract_address=market.collateral_token_contract_address_checksummed,
            amount_wei=amount_wei,
            from_address=from_address_checksummed,
            from_private_key=from_private_key,
        )
    # Buy shares using the deposited xDai in the collateral token.
    omen_buy_shares_tx(
        web3,
        market,
        amount_wei,
        outcome_index,
        expected_shares,
        from_address_checksummed,
        from_private_key,
    )


def binary_omen_buy_outcome_tx(
    amount: xDai,
    from_address: ChecksumAddress,
    from_private_key: PrivateKey,
    market: OmenAgentMarket,
    binary_outcome: bool,
    auto_deposit: bool,
) -> None:
    omen_buy_outcome_tx(
        amount=amount,
        from_address=from_address,
        from_private_key=from_private_key,
        market=market,
        outcome=OMEN_TRUE_OUTCOME if binary_outcome else OMEN_FALSE_OUTCOME,
        auto_deposit=auto_deposit,
    )


def omen_sell_outcome_tx(
    amount: xDai,
    from_address: ChecksumAddress,
    from_private_key: PrivateKey,
    market: OmenAgentMarket,
    outcome: str,
    auto_withdraw: bool,
) -> None:
    """
    Sells the given amount of shares for the given outcome in the given market.
    """
    web3 = Web3(Web3.HTTPProvider(GNOSIS_RPC_URL))
    amount_wei = xdai_to_wei(amount)
    from_address_checksummed = Web3.to_checksum_address(from_address)

    # Get the index of the outcome we want to buy.
    outcome_index: int = market.get_outcome_index(outcome)

    # Calculate the amount of shares we will sell for the given selling amount of xdai.
    max_outcome_tokens_to_sell = omen_calculate_sell_amount(
        web3, market, amount_wei, outcome_index
    )
    # Allow 1% slippage.
    max_outcome_tokens_to_sell = add_fraction(max_outcome_tokens_to_sell, 0.01)

    # Approve the market maker to move our (all) conditional tokens.
    omen_approve_all_market_maker_to_move_conditionaltokens_tx(
        web3=web3,
        market=market,
        approve=True,
        from_address=from_address_checksummed,
        from_private_key=from_private_key,
    )
    # Sell the shares.
    omen_sell_shares_tx(
        web3,
        market,
        amount_wei,
        outcome_index,
        max_outcome_tokens_to_sell,
        from_address_checksummed,
        from_private_key,
    )
    if auto_withdraw:
        # Optionally, withdraw from the collateral token back to the `from_address` wallet.
        omen_withdraw_collateral_token_tx(
            web3=web3,
            market=market,
            amount_wei=amount_wei,
            from_address=from_address_checksummed,
            from_private_key=from_private_key,
        )


def binary_omen_sell_outcome_tx(
    amount: xDai,
    from_address: ChecksumAddress,
    from_private_key: PrivateKey,
    market: OmenAgentMarket,
    binary_outcome: bool,
    auto_withdraw: bool,
) -> None:
    omen_sell_outcome_tx(
        amount=amount,
        from_address=from_address,
        from_private_key=from_private_key,
        market=market,
        outcome=OMEN_TRUE_OUTCOME if binary_outcome else OMEN_FALSE_OUTCOME,
        auto_withdraw=auto_withdraw,
    )


# Order by id, so we can use id_gt for pagination.
_QUERY_GET_FIXED_PRODUCT_MARKETS_MAKER_TRADES = """
query getFixedProductMarketMakerTrades(
    $id_gt: String!,
    $creator: String!,
    $creationTimestamp_gte: Int!,
    $creationTimestamp_lte: Int!,
    $first: Int!,
) {
    fpmmTrades(
        where: {
            type: Buy,
            creator: $creator,
            creationTimestamp_gte: $creationTimestamp_gte,
            creationTimestamp_lte: $creationTimestamp_lte,
            id_gt: $id_gt,
        }
        first: $first
        orderBy: id
        orderDirection: asc
    ) {
        id
        title
        collateralToken
        outcomeTokenMarginalPrice
        oldOutcomeTokenMarginalPrice
        type
        creator {
            id
        }
        creationTimestamp
        collateralAmount
        collateralAmountUSD
        feeAmount
        outcomeIndex
        outcomeTokensTraded
        transactionHash
        fpmm {
            id
            outcomes
            title
            answerFinalizedTimestamp
            currentAnswer
            isPendingArbitration
            arbitrationOccurred
            openingTimestamp
            condition {
                id
            }
        }
    }
}
"""


def to_int_timestamp(dt: datetime) -> int:
    return int(dt.timestamp())


def get_omen_bets(
    better_address: ChecksumAddress,
    start_time: datetime,
    end_time: t.Optional[datetime],
) -> list[OmenBet]:
    if not end_time:
        end_time = utcnow()

    # Initialize id_gt for the first batch of bets to zero
    id_gt: str = "0"
    all_bets: list[OmenBet] = []
    while True:
        query = _QUERY_GET_FIXED_PRODUCT_MARKETS_MAKER_TRADES
        bets = requests.post(
            THEGRAPH_QUERY_URL,
            json={
                "query": query,
                "variables": {
                    "creator": better_address.lower(),
                    "creationTimestamp_gte": to_int_timestamp(start_time),
                    "creationTimestamp_lte": to_int_timestamp(end_time),
                    "id_gt": id_gt,
                    "first": OMEN_QUERY_BATCH_SIZE,
                },
            },
            headers={"Content-Type": "application/json"},
        ).json()

        bets = bets.get("data", {}).get("fpmmTrades", [])

        if not bets:
            break

        # Increment id_gt for the next batch of bets
        id_gt = bets[-1]["id"]

        all_bets.extend(OmenBet.model_validate(bet) for bet in bets)

    return all_bets


def get_resolved_omen_bets(
    better_address: ChecksumAddress,
    start_time: datetime,
    end_time: t.Optional[datetime],
) -> list[OmenBet]:
    bets = get_omen_bets(
        better_address=better_address,
        start_time=start_time,
        end_time=end_time,
    )
    return [b for b in bets if b.fpmm.is_resolved]


def omen_realitio_ask_question_tx(
    web3: Web3,
    question: str,
    category: str,
    outcomes: list[str],
    language: str,
    arbitrator: Arbitrator,
    opening: datetime,
    from_address: ChecksumAddress,
    from_private_key: PrivateKey,
    nonce: int | None = None,
    tx_params: t.Optional[TxParams] = None,
) -> HexBytes:
    """
    After the question is created, you can find it at https://reality.eth.link/app/#!/creator/{from_address}.
    """
    arbitrator_contract_address, _ = get_arbitrator_contract_address_and_abi(arbitrator)
    # See https://realitio.github.io/docs/html/contracts.html#templates
    # for possible template ids and how to format the question.
    template_id = 2
    realitio_question = "␟".join(
        [
            question,
            json.dumps(outcomes),
            category,
            language,
        ]
    )
    receipt_tx = call_function_on_contract_tx(
        web3=web3,
        contract_address=OMEN_REALITIO_CONTRACT_ADDRESS,
        contract_abi=OMEN_REALITIO_ABI,
        from_address=from_address,
        from_private_key=from_private_key,
        function_name="askQuestion",
        function_params=dict(
            template_id=template_id,
            question=realitio_question,
            arbitrator=arbitrator_contract_address,
            timeout=86400,  # See https://github.com/protofire/omen-exchange/blob/2cfdf6bfe37afa8b169731d51fea69d42321d66c/app/src/util/networks.ts#L278.
            opening_ts=int(opening.timestamp()),
            nonce=(
                nonce if nonce is not None else random.randint(0, 1000000)
            ),  # Two equal questions need to have different nonces.
        ),
        tx_params=tx_params,
    )
    question_id: HexBytes = receipt_tx["logs"][0]["topics"][
        1
    ]  # The question id is available in the first emitted log, in the second topic.
    return question_id


def omen_construct_condition_id(
    web3: Web3,
    question_id: HexBytes,
    oracle_address: ChecksumAddress,
    outcomes_slot_count: int,
) -> HexBytes:
    id_: HexBytes = call_function_on_contract(
        web3,
        OMEN_FPMM_CONDITIONALTOKENS_CONTRACT_ADDRESS,
        OMEN_FPMM_CONDITIONALTOKENS_ABI,
        "getConditionId",
        [oracle_address, question_id, outcomes_slot_count],
    )
    return id_


def omen_does_condition_exist(
    web3: Web3,
    condition_id: HexBytes,
) -> bool:
    count: int = call_function_on_contract(
        web3,
        OMEN_FPMM_CONDITIONALTOKENS_CONTRACT_ADDRESS,
        OMEN_FPMM_CONDITIONALTOKENS_ABI,
        "getOutcomeSlotCount",
        [condition_id],
    )
    return count > 0


def omen_prepare_condition_tx(
    web3: Web3,
    question_id: HexBytes,
    oracle_address: ChecksumAddress,
    outcomes_slot_count: int,
    from_address: ChecksumAddress,
    from_private_key: PrivateKey,
    tx_params: t.Optional[TxParams] = None,
) -> None:
    call_function_on_contract_tx(
        web3=web3,
        contract_address=OMEN_FPMM_CONDITIONALTOKENS_CONTRACT_ADDRESS,
        contract_abi=OMEN_FPMM_CONDITIONALTOKENS_ABI,
        from_address=from_address,
        from_private_key=from_private_key,
        function_name="prepareCondition",
        function_params=[
            oracle_address,
            question_id,
            outcomes_slot_count,
        ],
        tx_params=tx_params,
    )


def omen_create_market_deposit_tx(
    initial_funds: xDai,
    from_address: ChecksumAddress,
    from_private_key: PrivateKey,
) -> TxReceipt | None:
    web3 = Web3(Web3.HTTPProvider(GNOSIS_RPC_URL))
    amount_wei = xdai_to_wei(initial_funds)
    balance = omen_get_balance_of_erc20_token(
        web3=web3,
        contract_address=DEFAULT_COLLATERAL_TOKEN_CONTRACT_ADDRESS,
        for_address=from_address,
    )
    if balance < amount_wei:
        return omen_deposit_collateral_token_tx(
            web3=web3,
            collateral_token_contract_address=DEFAULT_COLLATERAL_TOKEN_CONTRACT_ADDRESS,
            amount_wei=amount_wei,
            from_address=from_address,
            from_private_key=from_private_key,
        )
    else:
        return None


def omen_create_market_tx(
    initial_funds: xDai,
    question: str,
    closing_time: datetime,
    category: str,
    language: str,
    from_address: ChecksumAddress,
    from_private_key: PrivateKey,
    outcomes: list[str],
    auto_deposit: bool,
    fee: float = OMEN_DEFAULT_MARKET_FEE,
) -> ChecksumAddress:
    """
    Based on omen-exchange TypeScript code: https://github.com/protofire/omen-exchange/blob/b0b9a3e71b415d6becf21fe428e1c4fc0dad2e80/app/src/services/cpk/cpk.ts#L308
    """
    web3 = Web3(Web3.HTTPProvider(GNOSIS_RPC_URL))

    initial_funds_wei = xdai_to_wei(initial_funds)
    fee_wei = xdai_to_wei(
        xdai_type(fee)
    )  # We need to convert this to the wei units, but in reality it's % fee as stated in the `OMEN_DEFAULT_MARKET_FEE` variable.

    # These checks were originally maded somewhere in the middle of the process, but it's safer to do them right away.
    # Double check that the oracle's realitio address is the same as we are using.
    if (
        call_function_on_contract(
            web3,
            OMEN_ORACLE_CONTRACT_ADDRESS,
            OMEN_ORACLE_ABI,
            "realitio",
        )
        != OMEN_REALITIO_CONTRACT_ADDRESS
    ):
        raise RuntimeError(
            "The oracle's realitio address is not the same as we are using."
        )
    # Double check that the oracle's conditional tokens address is the same as we are using.
    if (
        call_function_on_contract(
            web3,
            OMEN_ORACLE_CONTRACT_ADDRESS,
            OMEN_ORACLE_ABI,
            "conditionalTokens",
        )
        != OMEN_FPMM_CONDITIONALTOKENS_CONTRACT_ADDRESS
    ):
        raise RuntimeError(
            "The oracle's conditional tokens address is not the same as we are using."
        )

    # Approve the market maker to withdraw our collateral token.
    omen_approve_market_maker_to_spend_collateral_token_tx(
        web3=web3,
        market_maker_contract_address=OMEN_FPMM_FACTORY_CONTRACT_ADDRESS,
        collateral_token_contract_address=DEFAULT_COLLATERAL_TOKEN_CONTRACT_ADDRESS,
        amount_wei=initial_funds_wei,
        from_address=from_address,
        from_private_key=from_private_key,
    )

    # Deposit xDai to the collateral token,
    # this can be skipped, if we know we already have enough collateral tokens.
    if auto_deposit and initial_funds_wei > 0:
        omen_create_market_deposit_tx(initial_funds, from_address, from_private_key)

    # Create the question on Realitio.
    question_id = omen_realitio_ask_question_tx(
        web3=web3,
        question=question,
        category=category,
        outcomes=outcomes,
        language=language,
        arbitrator=Arbitrator.KLEROS,
        opening=closing_time,  # The question is opened at the closing time of the market.
        from_address=from_address,
        from_private_key=from_private_key,
    )

    # Construct the condition id.
    condition_id = omen_construct_condition_id(
        web3=web3,
        question_id=question_id,
        oracle_address=OMEN_ORACLE_CONTRACT_ADDRESS,
        outcomes_slot_count=len(outcomes),
    )
    if not omen_does_condition_exist(web3, condition_id):
        omen_prepare_condition_tx(
            web3,
            question_id=question_id,
            oracle_address=OMEN_ORACLE_CONTRACT_ADDRESS,
            outcomes_slot_count=len(outcomes),
            from_address=from_address,
            from_private_key=from_private_key,
        )

    # Create the market.
    create_market_receipt_tx = call_function_on_contract_tx(
        web3=web3,
        contract_address=OMEN_FPMM_FACTORY_CONTRACT_ADDRESS,
        contract_abi=OMEN_FPMM_FACTORY_ABI,
        from_address=from_address,
        from_private_key=from_private_key,
        function_name="create2FixedProductMarketMaker",
        function_params=dict(
            saltNonce=random.randint(
                0, 1000000
            ),  # See https://github.com/protofire/omen-exchange/blob/923756c3a9ac370f8e89af8193393a53531e2c0f/app/src/services/cpk/fns.ts#L942.
            conditionalTokens=OMEN_FPMM_CONDITIONALTOKENS_CONTRACT_ADDRESS,
            collateralToken=DEFAULT_COLLATERAL_TOKEN_CONTRACT_ADDRESS,
            conditionIds=[condition_id],
            fee=fee_wei,
            initialFunds=initial_funds_wei,
            distributionHint=[],
        ),
    )

    # Note: In the Omen's Typescript code, there is futher a creation of `stakingRewardsFactoryAddress`,
    # (https://github.com/protofire/omen-exchange/blob/763d9c9d05ebf9edacbc1dbaa561aa5d08813c0f/app/src/services/cpk/fns.ts#L979)
    # but address of stakingRewardsFactoryAddress on xDai/Gnosis is 0x0000000000000000000000000000000000000000,
    # so skipping it here.

    market_address = create_market_receipt_tx["logs"][-1][
        "address"
    ]  # The market address is available in the last emitted log, in the address field.
    return market_address
