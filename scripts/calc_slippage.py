r_a = 10
r_b = 10
p_a = r_b / (r_a + r_b)
# alice buys YES (n_a) with b=10
X = 10
n_a = X * (r_a + r_b) / (2 * r_b)
n_b = X * (r_a + r_b) / (2 * r_a)
n_swap = r_a - ((r_a * r_b) / (r_b + ((X * (r_b + r_a)) / (2 * r_a))))
n_r = n_a + n_swap

p_a_new = X / n_r
slippage = (p_a_new - p_a) / p_a
print(f" p_a {p_a} n_swap {n_swap} p_a_new {p_a_new} slippage {slippage}")

# slippage = 0.3333
s = 1 / 5
bet_amount = p_a * (s + 1) * n_r
print(f"bet_amount {bet_amount}")
