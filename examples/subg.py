from subgrounds import Subgrounds

SUBGRAPH_URL = "https://api.thegraph.com/subgraphs/name/protofire/omen-xdai"
CREATOR = "0x2dd9f5678484c1f59f97ed334725858b938b4102"


def main():
    print("main")

    sg = Subgrounds()
    # Load the subgraph
    subgraph = sg.load_subgraph(SUBGRAPH_URL)

    # Construct the query
    latest_markets = subgraph.Query.fixedProductMarketMakers(
        orderBy=subgraph.FixedProductMarketMaker.creationTimestamp,
        # orderDirection="desc",
        first=2,
        # where=[],
    )
    df = sg.query_df(
        [
            latest_markets.id,
            latest_markets.question.id,
        ]
    )
    print(len(df))


if __name__ == "__main__":
    main()
