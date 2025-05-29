import asyncio

from hypersync import (
    ClientConfig,
    HypersyncClient,
    preset_query_logs,
)

from prediction_market_agent_tooling.markets.omen.omen_contracts import (
    OmenAgentResultMappingContract,
)


async def main():
    url = "https://indexer.dev.hyperindex.xyz/caf826f/v1/graphql"
    client = HypersyncClient(ClientConfig(url=url))
    # The query to run

    query = preset_query_logs(
        address=OmenAgentResultMappingContract().address, from_block=0
    )

    print("Running the query...")

    # Run the query once, the query is automatically paginated so it will return when it reaches some limit (time, response size etc.)
    # there is a next_block field on the response object so we can set the from_block of our query to this value and continue our query until
    # res.next_block is equal to res.archive_height or query.to_block in case we specified an end block.
    res = await client.get(query)

    print(f"Ran the query once.  Next block to query is {res.next_block}")

    # print(len(res.data.blocks))
    # print(len(res.data.transactions))
    print(len(res.data.logs))


if __name__ == "__main__":
    asyncio.run(main())
