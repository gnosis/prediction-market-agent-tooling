from prediction_market_agent_tooling.markets.omen.omen_subgraph_handler import (
    OmenSubgraphHandler,
)

if __name__ == "__main__":
    sh = OmenSubgraphHandler()
    q = sh.get_questions(claimed=True, limit=2)
    print(q)
