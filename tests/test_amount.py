from prediction_market_agent_tooling.tools.amount import DynamicAmount, StaticAmount


def test_static_amount() -> None:
    bet_amount = StaticAmount
    assert bet_amount(100).get() == 100


def test_dynamic_amount() -> None:
    def get_wallet_balance() -> float:
        return 23.1

    bet_amount = DynamicAmount(get_amount_fn=get_wallet_balance, proportion=0.1)
    assert bet_amount.get() == 2.31
