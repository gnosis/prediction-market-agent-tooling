import typing as t

from pydantic import BaseModel
from pydantic.types import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

from prediction_market_agent_tooling.gtypes import ChecksumAddress, PrivateKey
from prediction_market_agent_tooling.markets.manifold.api import get_authenticated_user
from prediction_market_agent_tooling.tools.utils import check_not_none
from prediction_market_agent_tooling.tools.web3_utils import private_key_to_public_key

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
    BET_FROM_PRIVATE_KEY: t.Optional[PrivateKey] = None
    SAFE_ADDRESS: t.Optional[ChecksumAddress] = None
    OPENAI_API_KEY: t.Optional[SecretStr] = None

    GOOGLE_SEARCH_API_KEY: t.Optional[SecretStr] = None
    GOOGLE_SEARCH_ENGINE_ID: t.Optional[SecretStr] = None

    ENABLE_CACHE: bool = True
    CACHE_DIR: str = "./.cache"

    @property
    def manifold_user_id(self) -> str:
        return get_authenticated_user(
            api_key=self.manifold_api_key.get_secret_value()
        ).id

    @property
    def manifold_api_key(self) -> SecretStr:
        return check_not_none(
            self.MANIFOLD_API_KEY, "MANIFOLD_API_KEY missing in the environment."
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

    @property
    def google_search_api_key(self) -> SecretStr:
        return check_not_none(
            self.GOOGLE_SEARCH_API_KEY,
            "GOOGLE_SEARCH_API_KEY missing in the environment.",
        )

    @property
    def google_search_engine_id(self) -> SecretStr:
        return check_not_none(
            self.GOOGLE_SEARCH_ENGINE_ID,
            "GOOGLE_SEARCH_ENGINE_ID missing in the environment.",
        )

    def model_dump_public(self) -> dict[str, t.Any]:
        return {
            k: v
            for k, v in self.model_dump().items()
            if APIKeys.model_fields[k].annotation not in SECRET_TYPES and v is not None
        }

    def model_dump_secrets(self) -> dict[str, t.Any]:
        return {
            k: v.get_secret_value() if isinstance(v, SecretStr) else v
            for k, v in self.model_dump().items()
            if APIKeys.model_fields[k].annotation in SECRET_TYPES and v is not None
        }


class PrivateCredentials(BaseModel):
    private_key: PrivateKey
    safe_address: ChecksumAddress | None

    @property
    def public_key(self) -> ChecksumAddress:
        """If the SAFE is available, we always route transactions via SAFE. Otherwise we use the EOA."""
        return (
            self.safe_address
            if self.safe_address is not None
            else private_key_to_public_key(self.private_key)
        )

    @property
    def has_safe_address(self) -> bool:
        return self.safe_address is not None

    @staticmethod
    def from_api_keys(api_keys: APIKeys) -> "PrivateCredentials":
        return PrivateCredentials(
            private_key=api_keys.bet_from_private_key,
            safe_address=api_keys.SAFE_ADDRESS,
        )
