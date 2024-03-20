import typing as t
from datetime import datetime

import requests
from eth_typing import ChecksumAddress, HexAddress

from prediction_market_agent_tooling.markets.agent_market import FilterBy, SortBy
from prediction_market_agent_tooling.markets.omen.data_models import (
    FixedProductMarketMakersResponse,
    OmenBet,
    OmenMarket,
    OmenUserPosition,
)
from prediction_market_agent_tooling.tools.utils import response_to_model, utcnow

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
    outcomes: list[str],
    sort_by: SortBy,
    filter_by: FilterBy,
    first: int = 1000,  # max limit for markets
    created_after: t.Optional[datetime] = None,
    creator: t.Optional[HexAddress] = None,
    excluded_questions: set[str] | None = None,
) -> list[OmenMarket]:
    """
    We return the first 1000 markets, since we don't have pagination in place (yet).
    """
    # ToDo
    #  One could use subgrounds for direct querying FixedProductMarketMakers.
    #  See https://github.com/gnosis/prediction-market-agent-tooling/issues/115
    order_by, order_direction = ordering_from_sort_by(sort_by)
    markets = response_to_model(
        requests.post(
            OMEN_TRADES_SUBGRAPH,
            json={
                "query": construct_query_get_fixed_product_markets_makers(
                    include_creator=creator is not None,
                    filter_by=filter_by,
                ),
                "variables": {
                    "first": first,
                    "outcomes": outcomes,
                    "orderBy": order_by,
                    "orderDirection": order_direction,
                    "creationTimestamp_gt": (
                        to_int_timestamp(created_after) if created_after else 0
                    ),
                    "creator": creator,
                },
            },
            headers={"Content-Type": "application/json"},
        ),
        FixedProductMarketMakersResponse,
    )
    return [
        m
        for m in markets.data.fixedProductMarketMakers
        if not excluded_questions or m.question not in excluded_questions
    ]


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
    query = _QUERY_GET_FIXED_PRODUCT_MARKETS_MAKER_TRADES

    while True:
        bets = requests.post(
            OMEN_TRADES_SUBGRAPH,
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
    start_time: datetime,
    end_time: t.Optional[datetime],
    better_address: ChecksumAddress,
) -> list[OmenBet]:
    bets = get_omen_bets(
        start_time=start_time,
        end_time=end_time,
        better_address=better_address,
    )
    return [b for b in bets if b.fpmm.is_resolved]
