from unittest.mock import patch

from pydantic import SecretStr

from prediction_market_agent_tooling.config import APIKeys
from prediction_market_agent_tooling.gtypes import PrivateKey


def test_gcp_secrets_empty() -> None:
    with patch.dict("os.environ", {}):
        api_keys = APIKeys()
        assert api_keys.BET_FROM_PRIVATE_KEY is None


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
