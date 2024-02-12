import typing as t
from pydantic_settings import BaseSettings, SettingsConfigDict
from prediction_market_agent_tooling.tools.utils import check_not_none
from prediction_market_agent_tooling.tools.web3_utils import verify_address
from prediction_market_agent_tooling.gtypes import ChecksumAddress, PrivateKey


class APIKeys(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    MANIFOLD_API_KEY: t.Optional[str] = None
    BET_FROM_ADDRESS: t.Optional[ChecksumAddress] = None
    BET_FROM_PRIVATE_KEY: t.Optional[PrivateKey] = None

    @property
    def manifold_api_key(self) -> str:
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
