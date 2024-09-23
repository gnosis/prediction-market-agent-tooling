from prediction_market_agent_tooling.tools.parallelism import par_generator, par_map


def test_par_map() -> None:
    l = list(range(100))
    f = lambda x: x**2
    results = par_map(l, f, max_workers=5)
    assert [f(x) for x in l] == results


def test_par_generator() -> None:
    l = list(range(100))
    f = lambda x: x**2
    results = par_generator(l, f, max_workers=5)
    assert [f(x) for x in l] == sorted(results)
