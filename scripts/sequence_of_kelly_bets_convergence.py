import numpy as np
from matplotlib import pyplot as plt

from prediction_market_agent_tooling.tools.betting_strategies.kelly_criterion import (
    get_kelly_bet_full,
)
from prediction_market_agent_tooling.tools.betting_strategies.market_moving import (
    get_market_moving_bet,
)

"""
if kelly moves market past mm bet, does subsequent market move back to mm bet?
"""


def get_p_yes_from_token_pool(token_pool: dict[bool, float]) -> float:
    return token_pool[False] / (token_pool[True] + token_pool[False])


def get_buy_amount(
    token_pool: dict[bool, float], bet_amount: float, direction: bool
) -> float:
    """
    y: yes outcome pool size
    n: no outcome pool size
    b: bet amount
    d: float(direction)
    d': float(not direction)
    c: market constant
    a: buy amount

    Initially:
    y * n = c

    After bet:
    (y + b - a.d).(n + b - a.d') = c

    Rearrange to solve for a:
    a = ((b + y)(b + n) - c) / (y.d' + n.d + b)
    """
    y = token_pool[True]
    n = token_pool[False]
    b = bet_amount
    c = y * n
    d = float(direction)
    d_prime = float(not direction)
    a = ((b + y) * (b + n) - c) / (y * d_prime + n * d + b)
    return a


def get_new_token_pool_after_bet(
    orig_token_pool: dict[bool, float], bet_amount: float, direction: bool
) -> dict[bool, float]:
    new_token_pool = orig_token_pool.copy()
    for outcome in [True, False]:
        new_token_pool[outcome] += bet_amount
    buy_amount = get_buy_amount(orig_token_pool, bet_amount, direction)
    new_token_pool[direction] -= buy_amount
    return new_token_pool


estimated_p_yes = 0.90
kelly_max_bet_mm_bet_ratios = [0.1, 0.2, 0.5, 1.0, 5, 10, 100, 1000, 10000]
colors = plt.cm.viridis(np.linspace(0, 1, len(kelly_max_bet_mm_bet_ratios)))
n_sequential_bets = 20

# Init token pool
outcome_token_pool = {
    True: 10.0,
    False: 11.0,
}

market_moving_bet = get_market_moving_bet(
    yes_outcome_pool_size=outcome_token_pool[True],
    no_outcome_pool_size=outcome_token_pool[False],
    market_p_yes=get_p_yes_from_token_pool(outcome_token_pool),
    target_p_yes=estimated_p_yes,
)

for i, bet_ratio in enumerate(kelly_max_bet_mm_bet_ratios):
    # Add initial p_yes
    p_yess = [get_p_yes_from_token_pool(outcome_token_pool)]
    updated_outcome_token_pool = outcome_token_pool.copy()

    for _ in range(n_sequential_bets):
        kelly_bet = get_kelly_bet_full(
            yes_outcome_pool_size=updated_outcome_token_pool[True],
            no_outcome_pool_size=updated_outcome_token_pool[False],
            estimated_p_yes=estimated_p_yes,
            confidence=1.0,
            max_bet=market_moving_bet.size * bet_ratio,
        )

        # Update token pool
        updated_outcome_token_pool = get_new_token_pool_after_bet(
            updated_outcome_token_pool, kelly_bet.size, kelly_bet.direction
        )
        p_yess.append(get_p_yes_from_token_pool(updated_outcome_token_pool))

    plt.plot(
        range(len(p_yess)),
        p_yess,
        label=f"kelly 'max bet':market-moving bet ratio = {bet_ratio}",
        color=colors[i],
        linestyle="-",
    )


plt.xlabel(f"Bet number")
plt.ylabel("Market p_yes")
plt.title("Kelly bet convergence to estimated_p_yes")
plt.legend(bbox_to_anchor=(1.05, 1), loc="upper left")
plt.tight_layout()
plt.show()
