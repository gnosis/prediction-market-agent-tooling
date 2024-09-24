from scipy.optimize import newton

from prediction_market_agent_tooling.markets.omen.omen import (
    get_buy_outcome_token_amount,
)


def calc_slippage(bet_amount, yes, no):
    initial_p_yes = no / (yes + no)
    expected_tokens_yes = bet_amount / initial_p_yes
    bought_yes = get_buy_outcome_token_amount(bet_amount, True, yes, no, 0)
    num = expected_tokens_yes - bought_yes
    den = expected_tokens_yes
    s = num / den
    print(f"slippage {s}")
    return s


if __name__ == "__main__":
    bet_amount = 2.84e18
    yes = 11767992330161487184
    no = 4163836840241006013
    decimals = 18
    # bet_amount = 10
    # yes = 10
    # no = 10
    # decimals = 0
    p_yes = no / (yes + no)
    print(f"initial p_yes {p_yes}")
    expected_yes = bet_amount / p_yes
    print(f"expected_yes {expected_yes}")
    bought_yes = get_buy_outcome_token_amount(bet_amount, True, yes, no, 0)
    print(f"bought yes {bought_yes}")
    # We can define slippage either considering the tokens you get by minting or not, i.e.
    # only consider the tokens you swap in the slippage calculation.
    slippage = (expected_yes - bought_yes) / expected_yes
    print(f"slippage {slippage}")
    # what is the new price?
    yes_prime = yes + bet_amount - bought_yes
    no_prime = no + bet_amount
    p_yes_prime = no_prime / (yes_prime + no_prime)
    print(f"p_yes_prime {p_yes_prime}")
    print(f"slippage calc {calc_slippage(bet_amount, yes, no)}")

    print(
        f"yes {yes/1e18} no {no/10**decimals} bought_yes {bought_yes/10**decimals} yes_prime {yes_prime/10**decimals} no_prime {no_prime/10**decimals} k_0  {yes*no/10**(2*decimals)} k_1 {yes_prime*no_prime/10**(2*decimals)}"
    )

    # say we want 30% slippage
    target_slippage = 0.3

    def f(b: float) -> float:
        actual_slippage = calc_slippage(b, yes, no)
        return actual_slippage - target_slippage

    optimized_bet_amount = newton(f, 1e18)
    print(f"optimized {optimized_bet_amount}")

    # Next steps - use target slippage to find bet amount
    # Create new strategy based on slippage for Kelly
    # Run simulations for that one
