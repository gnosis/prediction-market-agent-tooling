import os
import typing as t

from dotenv import load_dotenv
from pydantic import BaseModel

from prediction_market_agent_tooling.gtypes import ChecksumAddress, PrivateKey
from prediction_market_agent_tooling.tools.utils import check_not_none
from prediction_market_agent_tooling.tools.web3_utils import verify_address

load_dotenv()


class APIKeys(BaseModel):
    MANIFOLD_API_KEY: t.Optional[str] = os.getenv("MANIFOLD_API_KEY")
    BET_FROM_ADDRESS: t.Optional[ChecksumAddress] = os.getenv("BET_FROM_ADDRESS")
    BET_FROM_PRIVATE_KEY: t.Optional[PrivateKey] = os.getenv("BET_FROM_PRIVATE_KEY")

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
