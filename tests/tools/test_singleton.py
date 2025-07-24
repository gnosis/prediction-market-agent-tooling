from prediction_market_agent_tooling.tools.singleton import SingletonMeta


class TestSingleton(metaclass=SingletonMeta):
    increment = 0

    def __init__(self, x: int) -> None:
        self.x = x
        TestSingleton.increment += 1


def test_singleton_creation() -> None:
    a = TestSingleton(1)
    b = TestSingleton(1)

    c = TestSingleton(2)
    d = TestSingleton(2)

    assert a.x == b.x
    assert c.x != a.x
    assert c.x == d.x
    assert TestSingleton.increment == 2
