from prediction_market_agent_tooling.markets.polymarket.clob_manager import ClobManager


def test_get_fee_0() -> None:
    clob_manager = ClobManager()
    token_id = (
        18822812066819800310928467826996124926526029026598480680953086271904576052367
    )
    fee_rate = clob_manager.get_token_fee_rate(token_id=token_id)
    assert fee_rate > 0, "Sports should have fee"


def test_get_fee_1() -> None:
    clob_manager = ClobManager()
    token_id = (
        45570694128306235580101788040682653586361413197718007100284267278086814950441
    )
    fee_rate = clob_manager.get_token_fee_rate(token_id=token_id)
    assert fee_rate == 0, "Geopolitics should not have fee"
