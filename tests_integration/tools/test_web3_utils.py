from prediction_market_agent_tooling.tools.balances import get_balances
from prediction_market_agent_tooling.tools.web3_utils import (
    generate_private_key,
    private_key_to_public_key,
)


def test_generate_private_key() -> None:
    # Test that generate key is valid and has zero balance because it's fresh.
    private_key = generate_private_key()
    public_key = private_key_to_public_key(private_key)
    balances = get_balances(public_key)
    assert balances.total == 0
