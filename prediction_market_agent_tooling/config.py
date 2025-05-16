import json
import typing as t
from copy import deepcopy

from eth_account.signers.local import LocalAccount
from eth_typing import URI
from pydantic import Field, model_validator
from pydantic.types import SecretStr
from pydantic.v1.types import SecretStr as SecretStrV1
from pydantic_settings import BaseSettings, SettingsConfigDict
from safe_eth.eth import EthereumClient
from safe_eth.safe.safe import SafeV141
from web3 import Account, Web3

from prediction_market_agent_tooling.deploy.gcp.utils import gcp_get_secret_value
from prediction_market_agent_tooling.gtypes import (
    ChainID,
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
    SAFE_ADDRESS: str | None = None
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
    # Don't get fooled! Serper and Serp are two different services.
    SERPER_API_KEY: t.Optional[SecretStr] = None

    SQLALCHEMY_DB_URL: t.Optional[SecretStr] = None

    ENABLE_CACHE: bool = False
    CACHE_DIR: str = "./.cache"

    @model_validator(mode="before")
    @classmethod
    def _model_validator(cls, data: t.Any) -> t.Any:
        data = deepcopy(data)
        data = cls._replace_gcp_secrets(data)
        return data

    @staticmethod
    def _replace_gcp_secrets(data: t.Any) -> t.Any:
        if isinstance(data, dict):
            for k, v in data.items():
                # Check if the value is meant to be fetched from GCP Secret Manager, if so, replace it with it.
                if isinstance(v, (str, SecretStr)):
                    secret_value = (
                        v.get_secret_value() if isinstance(v, SecretStr) else v
                    )
                    if secret_value.startswith("gcps:"):
                        # We assume that secrets are dictionaries and the value is a key in the dictionary,
                        # example usage: `BET_FROM_PRIVATE_KEY=gcps:my-agent:private_key`
                        _, secret_name, key_name = secret_value.split(":")
                        secret_data = json.loads(gcp_get_secret_value(secret_name))[
                            key_name
                        ]
                        data[k] = secret_data
        else:
            raise ValueError("Data must be a dictionary.")
        return data

    def copy_without_safe_address(self) -> "APIKeys":
        """
        This is handy when you operate in environment with SAFE_ADDRESS, but need to execute transaction using EOA.
        """
        data = self.model_copy(deep=True)
        data.SAFE_ADDRESS = None
        return data

    @property
    def safe_address_checksum(self) -> ChecksumAddress | None:
        return (
            Web3.to_checksum_address(self.SAFE_ADDRESS) if self.SAFE_ADDRESS else None
        )

    @property
    def serper_api_key(self) -> SecretStr:
        return check_not_none(
            self.SERPER_API_KEY, "SERPER_API_KEY missing in the environment."
        )

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
        return (
            self.safe_address_checksum
            if self.safe_address_checksum
            else self.public_key
        )

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

    def get_account(self) -> LocalAccount:
        acc: LocalAccount = Account.from_key(
            self.bet_from_private_key.get_secret_value()
        )
        return acc

    def model_dump_public(self) -> dict[str, t.Any]:
        return {
            k: v
            for k, v in self.model_dump().items()
            if self.model_fields[k].annotation not in SECRET_TYPES and v is not None
        }

    def model_dump_secrets(self) -> dict[str, t.Any]:
        return {
            k: v.get_secret_value() if isinstance(v, SecretStr) else v
            for k, v in self.model_dump().items()
            if self.model_fields[k].annotation in SECRET_TYPES and v is not None
        }

    def check_if_is_safe_owner(self, ethereum_client: EthereumClient) -> bool:
        if not self.safe_address_checksum:
            raise ValueError("Cannot check ownership if safe_address is not defined.")

        s = SafeV141(self.safe_address_checksum, ethereum_client)
        public_key_from_signer = private_key_to_public_key(self.bet_from_private_key)
        return s.retrieve_is_owner(public_key_from_signer)


class RPCConfig(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    ETHEREUM_RPC_URL: URI = Field(default=URI("https://ethereum-rpc.publicnode.com"))
    GNOSIS_RPC_URL: URI = Field(default=URI("https://rpc.gnosischain.com"))
    CHAIN_ID: ChainID = Field(default=ChainID(100))

    @property
    def ethereum_rpc_url(self) -> URI:
        return check_not_none(
            self.ETHEREUM_RPC_URL, "ETHEREUM_RPC_URL missing in the environment."
        )

    @property
    def gnosis_rpc_url(self) -> URI:
        return check_not_none(
            self.GNOSIS_RPC_URL, "GNOSIS_RPC_URL missing in the environment."
        )

    @property
    def chain_id(self) -> ChainID:
        return check_not_none(self.CHAIN_ID, "CHAIN_ID missing in the environment.")

    def chain_id_to_rpc_url(self, chain_id: ChainID) -> URI:
        if chain_id == ChainID(1):
            return self.ethereum_rpc_url
        elif chain_id == ChainID(100):
            return self.gnosis_rpc_url
        else:
            raise ValueError(f"Unsupported chain ID: {chain_id}")

    def get_web3(self) -> Web3:
        return Web3(Web3.HTTPProvider(self.gnosis_rpc_url))


class CloudCredentials(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    GOOGLE_APPLICATION_CREDENTIALS: t.Optional[str] = None
