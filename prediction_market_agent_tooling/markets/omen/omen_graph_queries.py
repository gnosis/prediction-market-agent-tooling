import requests
from eth_typing import ChecksumAddress

from prediction_market_agent_tooling.markets.omen.data_models import OmenUserPosition
from prediction_market_agent_tooling.markets.omen.omen import (
    CONDITIONAL_TOKENS_SUBGRAPH,
    OMEN_QUERY_BATCH_SIZE,
)


def get_user_positions(
    better_address: ChecksumAddress,
) -> list[any]:
    # Initialize id_gt for the first batch of bets to zero
    id_gt: str = "0"
    all_user_positions: list[any] = []
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

        if not user_positions:
            break

        # Increment id_gt for the next batch of bets
        id_gt = user_positions[-1]["id"]

        all_user_positions.extend(
            OmenUserPosition.model_validate(user_position)
            for user_position in user_positions
        )

    return all_user_positions


USER_POSITIONS_QUERY = """
query($creator:String!, $id_gt: String!,  $first: Int!) {
  userPositions(where: {
    user: $creator,
    id_gt: $id_gt
  },
   first: $first
   orderBy: id
   orderDirection: desc) {
        id
        position {
            id
            conditionIds
    }
  }
}
"""
