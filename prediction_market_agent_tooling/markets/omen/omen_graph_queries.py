import typing as t
from datetime import datetime

import requests
from eth_typing import ChecksumAddress, HexAddress
from web3 import Web3
from typing import Callable

from prediction_market_agent_tooling.markets.agent_market import FilterBy, SortBy
from prediction_market_agent_tooling.markets.omen.data_models import (
    OmenBet,
    OmenMarket,
    OmenUserPosition,
)
from prediction_market_agent_tooling.tools.utils import utcnow

"""
Python API for Omen prediction market.

Their API is available as graph on https://thegraph.com/explorer/subgraphs/9V1aHHwkK4uPWgBH6ZLzwqFEkoHTHPS7XHKyjZWe8tEf?view=Overview&chain=mainnet,
but to not use our own credits, seems we can use their api deployment directly: https://api.thegraph.com/subgraphs/name/protofire/omen-xdai/graphql (link to the online playground)
"""

OMEN_QUERY_BATCH_SIZE = 500
OMEN_TRADES_SUBGRAPH = "https://api.thegraph.com/subgraphs/name/protofire/omen-xdai"
CONDITIONAL_TOKENS_SUBGRAPH = (
    "https://api.thegraph.com/subgraphs/name/gnosis/conditional-tokens-gc"
)
BET_START_TIME = datetime(2020, 1, 1)
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
            resolutionTimestamp
            currentAnswer
            isPendingArbitration
            arbitrationOccurred
            openingTimestamp
             question {
                    id
                    answerFinalizedTimestamp
                    currentAnswer                                  
            }
            condition {
                id
                outcomeSlotCount
            }
            collateralVolume
            usdVolume
            collateralToken
            outcomeTokenAmounts
            outcomeTokenMarginalPrices
            fee
            category
        }
    }
}
"""


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
        condition {
            id
            outcomeSlotCount
        }
        answerFinalizedTimestamp
        resolutionTimestamp
        currentAnswer
        question {
            id
            answerFinalizedTimestamp
            currentAnswer 
        }
    }
}
"""

USER_POSITIONS_QUERY = """
query($creator:String!, $id_gt: String!,  $first: Int!) {
  userPositions(where: {
    user: $creator,
    id_gt: $id_gt
  },
   first: $first
   orderBy: id
   orderDirection: asc) {
        id
        position {
            id
            conditionIds
    }
  }
}
"""


def to_int_timestamp(dt: datetime) -> int:
    return int(dt.timestamp())


def ordering_from_sort_by(sort_by: SortBy) -> tuple[str, str]:
    """
    Returns 'orderBy' and 'orderDirection' strings for the given SortBy.
    """
    if sort_by == SortBy.CLOSING_SOONEST:
        return "creationTimestamp", "desc"  # TODO make more accurate
    elif sort_by == SortBy.NEWEST:
        return "creationTimestamp", "desc"
    else:
        raise ValueError(f"Unknown sort_by: {sort_by}")


def get_user_positions(
    better_address: ChecksumAddress,
) -> t.List[OmenUserPosition]:
    # Initialize id_gt for the first batch of bets to zero
    id_gt: str = "0"
    all_user_positions: t.List[OmenUserPosition] = []
    while True:
        query = USER_POSITIONS_QUERY
        result = requests.post(
            CONDITIONAL_TOKENS_SUBGRAPH,
            json={
                "query": query,
                "variables": {
                    "creator": better_address.lower(),
                    "id_gt": id_gt,
                    "first": OMEN_QUERY_BATCH_SIZE,
                },
            },
            headers={"Content-Type": "application/json"},
        ).json()

        user_positions = result.get("data", {}).get("userPositions", [])
        print(f"fetched {len(user_positions)} items id_gt {id_gt}")
        if not user_positions:
            break

        # Increment id_gt for the next batch of bets
        id_gt = user_positions[-1]["id"]

        all_user_positions.extend(
            OmenUserPosition.model_validate(user_position)
            for user_position in user_positions
        )

    return all_user_positions


def get_market(market_id: str) -> OmenMarket:
    market = requests.post(
        OMEN_TRADES_SUBGRAPH,
        json={
            "query": _QUERY_GET_SINGLE_FIXED_PRODUCT_MARKET_MAKER,
            "variables": {
                "id": market_id,
            },
        },
        headers={"Content-Type": "application/json"},
    ).json()["data"]["fixedProductMarketMaker"]
    return OmenMarket.model_validate(market)


def construct_query_get_fixed_product_markets_makers(
    include_creator: bool, filter_by: FilterBy
) -> str:
    query = """
        query getFixedProductMarketMakers(
            $first: Int!,
            $outcomes: [String!],
            $orderBy: String!,
            $orderDirection: String!,
            $creationTimestamp_gt: Int!,
            $creator: Bytes = null,
        ) {
            fixedProductMarketMakers(
                where: {
                    isPendingArbitration: false,
                    outcomes: $outcomes
                    creationTimestamp_gt: $creationTimestamp_gt
                    creator: $creator,
                    answerFinalizedTimestamp: null
                    resolutionTimestamp_not: null
                },
                orderBy: creationTimestamp,
                orderDirection: desc,
                first: $first
            ) {
                id
                title
                collateralVolume
                usdVolume
                collateralToken
                outcomes
                outcomeTokenAmounts
                outcomeTokenMarginalPrices
                fee
                answerFinalizedTimestamp
                resolutionTimestamp
                currentAnswer
                creationTimestamp
                category
                question {
                    id
                    answerFinalizedTimestamp
                    currentAnswer                                  
                }
                condition {
                    id
                    outcomeSlotCount
                }
            }
        }
    """

    if filter_by == FilterBy.OPEN:
        query = query.replace("resolutionTimestamp_not: null", "")
    elif filter_by == FilterBy.RESOLVED:
        query = query.replace("answerFinalizedTimestamp: null", "")
    elif filter_by == FilterBy.NONE:
        query = query.replace("answerFinalizedTimestamp: null", "")
        query = query.replace("resolutionTimestamp_not: null", "")
    else:
        raise ValueError(f"Unknown filter_by: {filter_by}")

    if not include_creator:
        # If we aren't filtering by query, we need to remove it from where, otherwise "creator: null" will return 0 results.
        query = query.replace("creator: $creator,", "")

    return query


def get_omen_markets(
    sort_by: SortBy,
    filter_by: FilterBy,
    creator: t.Optional[HexAddress] = None,
    created_after: t.Optional[datetime] = None,
    limit: t.Optional[int] = None,
) -> list[OmenMarket]:
    """
    Instead of querying markets directly (currently it only returns 20), an easier way is to fetch
    all bets from the creator, and aggregate the bets by market, and finally return all unique markets.
    """
    # ToDo
    #  One could use subgrounds for direct querying FixedProductMarketMakers.
    #  See https://github.com/gnosis/prediction-market-agent-tooling/issues/115
    resolved_bets = get_resolved_omen_bets(
        start_time=BET_START_TIME,
        end_time=created_after,
        better_address=Web3.to_checksum_address(creator) if creator else None,
    )

    markets = []
    # We want only unique markets
    seen_unique_ids = set()
    for bet in resolved_bets:
        if bet.fpmm.id not in seen_unique_ids and bet.fpmm.is_binary:
            market = OmenMarket.model_validate(bet.fpmm)
            market_valid = validate_market_for_filter_condition(market, filter_by)
            if market_valid:
                markets.append(market)
            seen_unique_ids.add(bet.fpmm.id)

    # We always sort by creation_datetime - but reverse the order under
    # conditions below.
    sort_direction_reversed = False
    match sort_by:
        case SortBy.NEWEST:
            sort_direction_reversed = True
        case _:
            pass

    # We sort here since the Bets subgraph is sorted by ID due to its pagination logic.
    markets.sort(key=lambda x: x.creation_datetime, reverse=sort_direction_reversed)

    # We limit here after sorting has been done.
    if limit:
        return markets[:limit]
    return markets


def validate_market_for_filter_condition(
    market: OmenMarket, filterBy: FilterBy
) -> bool:
    match filterBy:
        case FilterBy.OPEN:
            return market.is_open
        case FilterBy.RESOLVED:
            return market.is_resolved
        case _:
            return True


def sort_markets_closing_soonest(market: OmenMarket) -> datetime:
    return market.creation_datetime


def sort_markets_newest(market: OmenMarket) -> datetime:
    return market.creation_datetime


def get_omen_bets(
    start_time: datetime,
    end_time: t.Optional[datetime],
    better_address: t.Optional[ChecksumAddress] = None,
) -> list[OmenBet]:
    if not end_time:
        end_time = utcnow()

    # Initialize id_gt for the first batch of bets to zero
    id_gt: str = "0"
    all_bets: list[OmenBet] = []
    query = _QUERY_GET_FIXED_PRODUCT_MARKETS_MAKER_TRADES

    # We filter by better_address if provided
    if better_address is None:
        query = query.replace("creator: $creator,", "")

    while True:
        bets = requests.post(
            OMEN_TRADES_SUBGRAPH,
            json={
                "query": query,
                "variables": {
                    "creator": better_address.lower() if better_address else "",
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

        for i, bet in enumerate(bets):
            try:
                for i, bet in enumerate(bets):
                    # We neglect non-binary markets, for ex fpmmId = 0x09ba10798a54f8830e3568a000e55981c493f043
                    if not bet["fpmm"]["outcomes"]:
                        continue
                    all_bets.append(OmenBet.model_validate(bet))
            except Exception as e:
                print(f"exception {e}")

        # all_bets.extend(OmenBet.model_validate(bet) for bet in bets)

    return all_bets


def get_resolved_omen_bets(
    start_time: datetime,
    end_time: t.Optional[datetime],
    better_address: t.Optional[ChecksumAddress] = None,
) -> list[OmenBet]:
    bets = get_omen_bets(
        start_time=start_time,
        end_time=end_time,
        better_address=better_address,
    )
    return [b for b in bets if b.fpmm.is_resolved]
