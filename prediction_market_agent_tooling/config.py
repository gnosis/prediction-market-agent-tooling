import typing as t

from gnosis.eth import EthereumClient
from gnosis.safe import Safe
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


class ModalApiKeys(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    MODAL_TOKEN_ID: t.Optional[SecretStr] = None
    MODAL_TOKEN_SECRET: t.Optional[SecretStr] = None


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

    LANGFUSE_SECRET_KEY: t.Optional[SecretStr] = None
    LANGFUSE_PUBLIC_KEY: t.Optional[SecretStr] = None
    LANGFUSE_HOST: t.Optional[str] = None

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
    def bet_from_address(self) -> ChecksumAddress:
        """If the SAFE is available, we always route transactions via SAFE. Otherwise we use the EOA."""
        return (
            self.SAFE_ADDRESS
            if self.SAFE_ADDRESS
            else private_key_to_public_key(self.bet_from_private_key)
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

    @property
    def langfuse_secret_key(self) -> SecretStr:
        return check_not_none(
            self.LANGFUSE_SECRET_KEY, "LANGFUSE_SECRET_KEY missing in the environment."
        )

    @property
    def langfuse_public_key(self) -> SecretStr:
        return check_not_none(
            self.LANGFUSE_PUBLIC_KEY, "LANGFUSE_PUBLIC_KEY missing in the environment."
        )

    @property
    def langfuse_host(self) -> str:
        return check_not_none(
            self.LANGFUSE_HOST, "LANGFUSE_HOST missing in the environment."
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

    def check_if_is_safe_owner(self, ethereum_client: EthereumClient) -> bool:
        if not self.SAFE_ADDRESS:
            raise ValueError("Cannot check ownership if safe_address is not defined.")

        s = Safe(self.SAFE_ADDRESS, ethereum_client)  # type: ignore[abstract]
        public_key_from_signer = private_key_to_public_key(self.bet_from_private_key)
        return s.retrieve_is_owner(public_key_from_signer)
