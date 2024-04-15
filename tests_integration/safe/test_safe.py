import pytest
from eth_account import Account
from gnosis.eth import EthereumClient
from gnosis.safe import Safe

from prediction_market_agent_tooling.tools.safe import create_safe
from tests.utils import RUN_PAID_TESTS
from tests_integration.safe.test_constants import ANVIL_PKEY1


@pytest.mark.skipif(not RUN_PAID_TESTS, reason="This test costs money to run.")
def test_create_safe() -> None:
    # ToDo - Implement this when this issue has been merged (https://github.com/gnosis/prediction-market-agent-tooling/issues/99)
    #  Start local chain (fork Gnosis)
    #  Call create safe - for inspiration -> https://github.com/karpatkey/roles_royce/blob/2529d244ed8502d34f9daa9f70fa80e7b1123937/tests/utils.py#L77
    # create_safe(from_private_key=private_key_anvil1)
    #  Assert safe is valid, safe version 1.4.1
    #  Stop local chain
    ethereum_client = EthereumClient()

    account = Account.from_key(ANVIL_PKEY1)
    safe_address = create_safe(
        ethereum_client=ethereum_client,
        account=account,
        owners=[account.address],
        salt_nonce=42,
        threshold=1,
    )
    deployed_safe = Safe(safe_address, ethereum_client)
    version = deployed_safe.retrieve_version()
    assert version == "1.4.1"
    assert ethereum_client.is_contract(safe_address)
    assert deployed_safe.retrieve_owners() == [account.address]
