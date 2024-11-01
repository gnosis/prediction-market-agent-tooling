import typing as t

from pydantic.types import SecretStr
from pydantic.v1.types import SecretStr as SecretStrV1
from pydantic_settings import BaseSettings, SettingsConfigDict
from safe_eth.eth import EthereumClient
from safe_eth.safe.safe import SafeV141

from prediction_market_agent_tooling.gtypes import (
    ChecksumAddress,
    PrivateKey,
    secretstr_to_v1_secretstr,
)
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
    METACULUS_API_KEY: t.Optional[SecretStr] = None
    METACULUS_USER_ID: t.Optional[int] = None
    BET_FROM_PRIVATE_KEY: t.Optional[PrivateKey] = None
    SAFE_ADDRESS: t.Optional[ChecksumAddress] = None
    OPENAI_API_KEY: t.Optional[SecretStr] = None
    GRAPH_API_KEY: t.Optional[SecretStr] = None
    TENDERLY_FORK_RPC: t.Optional[str] = None

    GOOGLE_SEARCH_API_KEY: t.Optional[SecretStr] = None
    GOOGLE_SEARCH_ENGINE_ID: t.Optional[SecretStr] = None

    LANGFUSE_SECRET_KEY: t.Optional[SecretStr] = None
    LANGFUSE_PUBLIC_KEY: t.Optional[str] = None
    LANGFUSE_HOST: t.Optional[str] = None
    LANGFUSE_DEPLOYMENT_VERSION: t.Optional[str] = None

    ENABLE_IPFS_UPLOAD: bool = False
    PINATA_API_KEY: t.Optional[SecretStr] = None
    PINATA_API_SECRET: t.Optional[SecretStr] = None

    TAVILY_API_KEY: t.Optional[SecretStr] = None

    SQLALCHEMY_DB_URL: t.Optional[SecretStr] = None

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
    def metaculus_api_key(self) -> SecretStr:
        return check_not_none(
            self.METACULUS_API_KEY, "METACULUS_API_KEY missing in the environment."
        )

    @property
    def metaculus_user_id(self) -> int:
        return check_not_none(
            self.METACULUS_USER_ID, "METACULUS_USER_ID missing in the environment."
        )

    @property
    def bet_from_private_key(self) -> PrivateKey:
        return check_not_none(
            self.BET_FROM_PRIVATE_KEY,
            "BET_FROM_PRIVATE_KEY missing in the environment.",
        )

    @property
    def public_key(self) -> ChecksumAddress:
        return private_key_to_public_key(self.bet_from_private_key)

    @property
    def bet_from_address(self) -> ChecksumAddress:
        """If the SAFE is available, we always route transactions via SAFE. Otherwise we use the EOA."""
        return self.SAFE_ADDRESS if self.SAFE_ADDRESS else self.public_key

    @property
    def openai_api_key(self) -> SecretStr:
        return check_not_none(
            self.OPENAI_API_KEY, "OPENAI_API_KEY missing in the environment."
        )

    @property
    def openai_api_key_secretstr_v1(self) -> SecretStrV1:
        return secretstr_to_v1_secretstr(self.openai_api_key)

    @property
    def graph_api_key(self) -> SecretStr:
        return check_not_none(
            self.GRAPH_API_KEY, "GRAPH_API_KEY missing in the environment."
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
    def langfuse_public_key(self) -> str:
        return check_not_none(
            self.LANGFUSE_PUBLIC_KEY, "LANGFUSE_PUBLIC_KEY missing in the environment."
        )

    @property
    def langfuse_host(self) -> str:
        return check_not_none(
            self.LANGFUSE_HOST, "LANGFUSE_HOST missing in the environment."
        )

    @property
    def default_enable_langfuse(self) -> bool:
        return (
            self.LANGFUSE_SECRET_KEY is not None
            and self.LANGFUSE_PUBLIC_KEY is not None
            and self.LANGFUSE_HOST is not None
        )

    @property
    def enable_ipfs_upload(self) -> bool:
        return check_not_none(
            self.ENABLE_IPFS_UPLOAD, "ENABLE_IPFS_UPLOAD missing in the environment."
        )

    @property
    def pinata_api_key(self) -> SecretStr:
        return check_not_none(
            self.PINATA_API_KEY, "PINATA_API_KEY missing in the environment."
        )

    @property
    def pinata_api_secret(self) -> SecretStr:
        return check_not_none(
            self.PINATA_API_SECRET, "PINATA_API_SECRET missing in the environment."
        )

    @property
    def tavily_api_key(self) -> SecretStr:
        return check_not_none(
            self.TAVILY_API_KEY, "TAVILY_API_KEY missing in the environment."
        )

    @property
    def sqlalchemy_db_url(self) -> SecretStr:
        return check_not_none(
            self.SQLALCHEMY_DB_URL, "SQLALCHEMY_DB_URL missing in the environment."
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

        s = SafeV141(self.SAFE_ADDRESS, ethereum_client)
        public_key_from_signer = private_key_to_public_key(self.bet_from_private_key)
        return s.retrieve_is_owner(public_key_from_signer)
