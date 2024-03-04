import typing as t

from pydantic.types import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

from prediction_market_agent_tooling.gtypes import ChecksumAddress, PrivateKey
from prediction_market_agent_tooling.tools.utils import check_not_none
from prediction_market_agent_tooling.tools.web3_utils import verify_address

SECRET_TYPES = [
    SecretStr,
    PrivateKey,
    t.Optional[SecretStr],
    t.Optional[PrivateKey],
]


class APIKeys(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    MANIFOLD_API_KEY: t.Optional[SecretStr] = None
    BET_FROM_ADDRESS: t.Optional[ChecksumAddress] = None
    BET_FROM_PRIVATE_KEY: t.Optional[PrivateKey] = None
    OPENAI_API_KEY: t.Optional[SecretStr] = None

    ENABLE_CACHE: bool = True
    CACHE_DIR: str = "./.cache"

    @property
    def manifold_api_key(self) -> SecretStr:
        return check_not_none(
            self.MANIFOLD_API_KEY, "MANIFOLD_API_KEY missing in the environment."
        )

    @property
    def bet_from_address(self) -> ChecksumAddress:
        return verify_address(
            check_not_none(
                self.BET_FROM_ADDRESS,
                "BET_FROM_ADDRESS missing in the environment.",
            )
        )

    @property
    def bet_from_private_key(self) -> PrivateKey:
        return check_not_none(
            self.BET_FROM_PRIVATE_KEY,
            "BET_FROM_PRIVATE_KEY missing in the environment.",
        )

    @property
    def openai_api_key(self) -> SecretStr:
        return check_not_none(
            self.OPENAI_API_KEY, "OPENAI_API_KEY missing in the environment."
        )

    def model_dump_public(self) -> dict[str, t.Any]:
        return {
            k: v
            for k, v in self.model_dump().items()
            if APIKeys.model_fields[k].annotation not in SECRET_TYPES
        }

    def model_dump_secrets(self) -> dict[str, t.Any]:
        return {
            k: v.get_secret_value() if isinstance(v, SecretStr) else v
            for k, v in self.model_dump().items()
            if APIKeys.model_fields[k].annotation in SECRET_TYPES
        }
