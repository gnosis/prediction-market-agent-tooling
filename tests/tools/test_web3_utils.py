from prediction_market_agent_tooling.tools.web3_utils import private_key_to_public_key
from pydantic.types import SecretStr


def test_private_key_to_public_key() -> None:
    ganache_private_key_example = (
        "0x94c589f92a38698b984605efbc0bff47208c43eac85ab6ea553cc9e17c4a49fe"
    )
    ganache_public_key_example = "0x4c24e51488429E013f259A7FB6Ac174c715BB66a"
    actual_public_key = private_key_to_public_key(
        SecretStr(ganache_private_key_example)
    )
    assert actual_public_key == ganache_public_key_example
