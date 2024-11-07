import typer
from web3 import Web3

from prediction_market_agent_tooling.markets.omen.omen import OmenSubgraphHandler


def main(public_key: str) -> None:
    public_key_checksummed = Web3.to_checksum_address(public_key)

    all_bets = [
        bet
        for bet in OmenSubgraphHandler().get_bets(
            better_address=public_key_checksummed,
            filter_by_answer_finalized_not_null=True,
        )
        if bet.fpmm.is_resolved_with_valid_answer
    ]
    correct_bets = [
        bet for bet in all_bets if bet.boolean_outcome == bet.fpmm.boolean_outcome
    ]

    all_bets_with_results = []
    all_bets_without_results = []
    correct_results = []
    for bet in all_bets:
        result = OmenSubgraphHandler().get_agent_results_for_bet(bet)
        if result is None:
            all_bets_without_results.append(bet)
            continue
        all_bets_with_results.append(bet)
        if result.boolean_outcome == bet.fpmm.boolean_outcome:
            correct_results.append(result)

    print("N bets:", len(all_bets))
    print("Bet accuracy:", len(correct_bets) / len(all_bets) if all_bets else None)
    print(
        "Prediction accuracy:",
        len(correct_results) / len(all_bets_with_results) if all_bets else None,
    )
    print("N bets without results:", len(all_bets_without_results))


if __name__ == "__main__":
    typer.run(main)
