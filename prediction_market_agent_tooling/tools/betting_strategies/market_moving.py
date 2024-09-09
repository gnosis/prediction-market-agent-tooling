from functools import reduce

import numpy as np

from prediction_market_agent_tooling.gtypes import Probability
from prediction_market_agent_tooling.tools.betting_strategies.utils import SimpleBet


def get_market_moving_bet(
    yes_outcome_pool_size: float,
    no_outcome_pool_size: float,
    market_p_yes: float,
    target_p_yes: float,
    fee: float = 0.0,  # proportion, 0 to 1
    max_iters: int = 100,
) -> SimpleBet:
    """
    Implements a binary search to determine the bet that will move the market's
    `p_yes` to that of the target.

    Consider a binary fixed-product market containing `x` and `y` tokens.
    A trader wishes to aquire `x` tokens by betting an amount `d0`.

    The calculation to determine the number of `x` tokens he acquires, denoted
    by `dx`, is:

    a_x * a_y = fixed_product
    na_x = a_x + d0
    na_y = a_y + d0
    na_x * na_y = new_product
    (na_x - dx) * na_y = fixed_product
    (na_x * na_y) - (dx * na_y) = fixed_product
    new_product - fixed_product = dx * na_y
    dx = (new_product - fixed_product) / na_y
    """
    fixed_product = yes_outcome_pool_size * no_outcome_pool_size
    bet_direction: bool = True if target_p_yes > market_p_yes else False

    min_bet_amount = 0.0
    max_bet_amount = 100 * (
        yes_outcome_pool_size + no_outcome_pool_size
    )  # TODO set a better upper bound

    # Binary search for the optimal bet amount
    for _ in range(max_iters):
        bet_amount = (min_bet_amount + max_bet_amount) / 2
        amounts_diff = bet_amount * (1 - fee)

        # Initial new amounts are old amounts + equal new amounts for each outcome
        yes_outcome_new_pool_size = yes_outcome_pool_size + amounts_diff
        no_outcome_new_pool_size = no_outcome_pool_size + amounts_diff
        new_amounts = {
            True: yes_outcome_new_pool_size,
            False: no_outcome_new_pool_size,
        }

        # Now give away tokens at `bet_outcome_index` to restore invariant
        new_product = yes_outcome_new_pool_size * no_outcome_new_pool_size
        dx = (new_product - fixed_product) / new_amounts[not bet_direction]
        new_amounts[bet_direction] -= dx

        # Check that the invariant is restored
        assert np.isclose(
            reduce(lambda x, y: x * y, list(new_amounts.values()), 1.0),
            float(fixed_product),
        )

        new_p_yes = Probability(new_amounts[False] / sum(list(new_amounts.values())))
        if abs(target_p_yes - new_p_yes) < 0.01:
            break
        elif new_p_yes > target_p_yes:
            if bet_direction:
                max_bet_amount = bet_amount
            else:
                min_bet_amount = bet_amount
        else:
            if bet_direction:
                min_bet_amount = bet_amount
            else:
                max_bet_amount = bet_amount

    return SimpleBet(direction=bet_direction, size=bet_amount)
