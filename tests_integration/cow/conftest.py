import typing as t

import pytest
from eth_account import Account
from eth_account.signers.local import LocalAccount
from pydantic_settings import BaseSettings, SettingsConfigDict

from prediction_market_agent_tooling.gtypes import PrivateKey
from prediction_market_agent_tooling.tools.utils import check_not_none


class CowswapKey(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )
    COWSWAP_TEST_PRIVATE_KEY: t.Optional[PrivateKey] = None

    @property
    def cowswap_test_private_key(self) -> PrivateKey:
        return check_not_none(
            self.COWSWAP_TEST_PRIVATE_KEY,
            "COWSWAP_TEST_PRIVATE_KEY missing in the environment.",
        )


@pytest.fixture(scope="module")
def cowswap_test_account() -> t.Generator[LocalAccount, None, None]:
    # We use as cowswap account the market creator from a hackathon (public_key 0xa7E93F5A0e718bDDC654e525ea668c64Fd572882).
    key = CowswapKey()
    yield Account.from_key(key.cowswap_test_private_key.get_secret_value())
