import numpy as np
import pytest
from matplotlib import pyplot as plt

from prediction_market_agent_tooling.markets.agent_market import FilterBy, SortBy
from prediction_market_agent_tooling.markets.omen.omen import OmenAgentMarket
from prediction_market_agent_tooling.tools.betting_strategies.kelly_criterion import (
    get_kelly_bet_full,
)
from prediction_market_agent_tooling.tools.betting_strategies.market_moving import (
    _sanity_check_omen_market_moving_bet,
    get_market_moving_bet,
)

market = OmenAgentMarket.get_binary_markets(
    limit=1,
    sort_by=SortBy.CLOSING_SOONEST,
    filter_by=FilterBy.OPEN,
)[0]

yes_outcome_pool_size = market.outcome_token_pool[
    market.get_outcome_str_from_bool(True)
]
no_outcome_pool_size = market.outcome_token_pool[
    market.get_outcome_str_from_bool(False)
]
max_bets = np.linspace(0.0, 200, 100)

# Define a list of colors for different estimated_p_yes values
colors = plt.cm.viridis(np.linspace(0, 1, len([0.05, 0.42, 0.71])))

for i, estimated_p_yes in enumerate([0.57, 0.74, 0.92]):
    kelly_bets = []
    market_moving_bets = []
    kelly_expected_values = []
    market_moving_bet = get_market_moving_bet(
        yes_outcome_pool_size=yes_outcome_pool_size,
        no_outcome_pool_size=no_outcome_pool_size,
        market_p_yes=market.current_p_yes,
        target_p_yes=estimated_p_yes,
        fee=market.fee,
    )
    _sanity_check_omen_market_moving_bet(market_moving_bet, market, estimated_p_yes)

    market_moving_bet_signed = (
        market_moving_bet.size
        if market_moving_bet.direction == True
        else -market_moving_bet.size
    )

    for max_bet in max_bets:
        kelly_bet = get_kelly_bet_full(
            yes_outcome_pool_size=yes_outcome_pool_size,
            no_outcome_pool_size=no_outcome_pool_size,
            estimated_p_yes=estimated_p_yes,
            confidence=1.0,
            max_bet=max_bet,
            fee=market.fee,
        )
        kelly_bet_signed = (
            kelly_bet.size if kelly_bet.direction == True else -kelly_bet.size
        )
        kelly_bets.append(kelly_bet_signed)
        market_moving_bets.append(market_moving_bet_signed)

        # Calculate expected value for kelly bet
        p_correct = estimated_p_yes if kelly_bet.direction else 1 - estimated_p_yes
        tokens_bought = market.get_buy_token_amount(
            market.get_bet_amount(kelly_bet.size), kelly_bet.direction
        )
        expected_value = (tokens_bought.amount * p_correct) - (
            kelly_bet.size * (1 - p_correct)
        )
        kelly_expected_values.append(expected_value)

        # Kelly bet does not converge to market-moving bet. Is that expected? Yes!
        if max_bet == max_bets[-1]:
            with pytest.raises(ValueError) as e:
                _sanity_check_omen_market_moving_bet(kelly_bet, market, estimated_p_yes)
            assert e.match("Bet does not move market to target_p_yes")

    plt.plot(
        max_bets,
        kelly_bets,
        label=f"Kelly bet, {estimated_p_yes=:.2f}",
        color=colors[i],
        linestyle="-",
    )
    plt.plot(
        max_bets,
        market_moving_bets,
        label=f"Market-moving bet, target_p_yes={estimated_p_yes:.2f}",
        color=colors[i],
        linestyle="--",
    )
    plt.plot(
        max_bets,
        kelly_expected_values,
        label=f"Kelly bet EV, target_p_yes={estimated_p_yes:.2f}",
        color=colors[i],
        linestyle="-.",
    )

plt.xlabel(f"Max bet (xDai)")
plt.ylabel("Kelly bet size (xDai)")
plt.title(
    f"Market-moving vs. kelly bet, market_p_yes={market.current_p_yes:.2f}, pool_size={(yes_outcome_pool_size+no_outcome_pool_size):.2f}"
)
plt.legend(bbox_to_anchor=(1.05, 1), loc="upper left")
plt.tight_layout()
plt.show()
