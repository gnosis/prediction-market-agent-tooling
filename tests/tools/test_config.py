from unittest.mock import patch

import pytest
from pydantic import SecretStr

from prediction_market_agent_tooling.config import APIKeys
from prediction_market_agent_tooling.gtypes import PrivateKey


def test_gcp_secrets_empty() -> None:
    with patch.dict("os.environ", {}):
        api_keys = APIKeys()
        assert api_keys


def test_gcp_secrets_from_env_plain() -> None:
    with patch.dict("os.environ", {"BET_FROM_PRIVATE_KEY": "secret"}):
        api_keys = APIKeys()
        assert api_keys.bet_from_private_key.get_secret_value() == "secret"


def test_gcp_secrets_from_env_gcp() -> None:
    with patch.dict("os.environ", {"BET_FROM_PRIVATE_KEY": "gcps:test:key"}), patch(
        "prediction_market_agent_tooling.config.gcp_get_secret_value",
        return_value='{"key": "test_secret"}',
    ):
        api_keys = APIKeys()
        assert api_keys.bet_from_private_key.get_secret_value() == "test_secret"


def test_gcp_secrets_from_kwargs_plain() -> None:
    api_keys = APIKeys(BET_FROM_PRIVATE_KEY=PrivateKey(SecretStr("test_secret")))
    assert api_keys.bet_from_private_key.get_secret_value() == "test_secret"


def test_gcp_secrets_from_kwargs_gcp() -> None:
    with patch(
        "prediction_market_agent_tooling.config.gcp_get_secret_value",
        return_value='{"key": "test_secret"}',
    ):
        api_keys = APIKeys(BET_FROM_PRIVATE_KEY=PrivateKey(SecretStr("gcps:test:key")))
        assert api_keys.bet_from_private_key.get_secret_value() == "test_secret"


def test_gcp_secrets_from_dict_plain() -> None:
    api_keys = APIKeys.model_validate({"BET_FROM_PRIVATE_KEY": "test_secret"})
    assert api_keys.bet_from_private_key.get_secret_value() == "test_secret"


def test_gcp_secrets_from_dict_gcp() -> None:
    with patch(
        "prediction_market_agent_tooling.config.gcp_get_secret_value",
        return_value='{"key": "test_secret"}',
    ):
        api_keys = APIKeys.model_validate({"BET_FROM_PRIVATE_KEY": "gcps:test:key"})
        assert api_keys.bet_from_private_key.get_secret_value() == "test_secret"


@pytest.mark.parametrize(
    "safe_address, expected",
    [
        (
            "0xe91d153e0b41518a2ce8dd3d7944fa863463a97d",
            "0xe91D153E0b41518A2Ce8Dd3D7944Fa863463a97d",
        ),
        (None, None),
        (
            "0xe91D153E0b41518A2Ce8Dd3D7944Fa863463a97d",
            "0xe91D153E0b41518A2Ce8Dd3D7944Fa863463a97d",
        ),
    ],
)
def test_safe_is_checksummed(safe_address: str, expected: str) -> None:
    api_keys = APIKeys.model_validate({"SAFE_ADDRESS": safe_address})
    assert api_keys.safe_address_checksum == expected
