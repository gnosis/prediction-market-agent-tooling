import typing as t
from datetime import timedelta
from typing import Annotated
from urllib.parse import urljoin

from pydantic import BaseModel, BeforeValidator, ConfigDict, Field
from web3 import Web3
from web3.constants import ADDRESS_ZERO

from prediction_market_agent_tooling.config import RPCConfig
from prediction_market_agent_tooling.gtypes import (
    ChecksumAddress,
    HexAddress,
    HexBytes,
    OutcomeStr,
    OutcomeWei,
    Web3Wei,
    Wei,
)
from prediction_market_agent_tooling.markets.seer.subgraph_data_models import (
    SeerParentMarket,
)
from prediction_market_agent_tooling.tools.contract import ContractERC20OnGnosisChain
from prediction_market_agent_tooling.tools.datetime_utc import DatetimeUTC
from prediction_market_agent_tooling.tools.utils import utcnow


class CreateCategoricalMarketsParams(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    market_name: str = Field(..., alias="marketName")
    outcomes: t.Sequence[OutcomeStr]
    # Only relevant for scalar markets
    question_start: str = Field(alias="questionStart", default="")
    question_end: str = Field(alias="questionEnd", default="")
    outcome_type: str = Field(alias="outcomeType", default="")

    # Not needed for non-conditional markets.
    parent_outcome: int = Field(alias="parentOutcome", default=0)
    parent_market: HexAddress = Field(alias="parentMarket", default=ADDRESS_ZERO)

    category: str
    lang: str
    lower_bound: int = Field(alias="lowerBound", default=0)
    upper_bound: int = Field(alias="upperBound", default=0)
    min_bond: Web3Wei = Field(..., alias="minBond")
    opening_time: int = Field(..., alias="openingTime")
    token_names: list[str] = Field(..., alias="tokenNames")


SEER_BASE_URL = "https://app.seer.pm"


def seer_normalize_wei(value: int | None) -> int | None:
    # See https://github.com/seer-pm/demo/blob/main/web/netlify/edge-functions/utils/common.ts#L22
    if value is None:
        return value
    is_in_wei = value > 1e10
    return value if is_in_wei else value * 10**18


SeerNormalizedWei = Annotated[Wei | None, BeforeValidator(seer_normalize_wei)]


class SeerMarket(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    id: HexBytes
    creator: HexAddress
    title: str = Field(alias="marketName")
    outcomes: t.Sequence[OutcomeStr]
    wrapped_tokens: list[HexAddress] = Field(alias="wrappedTokens")
    parent_outcome: int = Field(alias="parentOutcome")
    parent_market: t.Optional[SeerParentMarket] = Field(
        alias="parentMarket", default=None
    )
    collateral_token: HexAddress = Field(alias="collateralToken")
    condition_id: HexBytes = Field(alias="conditionId")
    opening_ts: int = Field(alias="openingTs")
    block_timestamp: int = Field(alias="blockTimestamp")
    has_answers: bool | None = Field(alias="hasAnswers")
    payout_reported: bool = Field(alias="payoutReported")
    payout_numerators: list[int] = Field(alias="payoutNumerators")
    outcomes_supply: int = Field(alias="outcomesSupply")
    upper_bound: SeerNormalizedWei = Field(alias="upperBound", default=None)
    lower_bound: SeerNormalizedWei = Field(alias="lowerBound", default=None)

    @property
    def has_valid_answer(self) -> bool:
        # We assume that, for the market to be resolved as invalid, it must have both:
        # 1. An invalid outcome AND
        # 2. Invalid payoutNumerator is 1.

        return self.payout_reported and self.payout_numerators[-1] != 1

    @property
    def is_resolved(self) -> bool:
        return self.payout_reported

    @property
    def is_resolved_with_valid_answer(self) -> bool:
        return self.is_resolved and self.has_valid_answer

    def is_redeemable(self, owner: ChecksumAddress, web3: Web3 | None = None) -> bool:
        token_balances = self.get_outcome_token_balances(owner, web3)
        if not self.payout_reported:
            return False
        return any(
            payout and balance > 0
            for payout, balance in zip(self.payout_numerators, token_balances)
        )

    def get_outcome_token_balances(
        self, owner: ChecksumAddress, web3: Web3 | None = None
    ) -> list[OutcomeWei]:
        return [
            OutcomeWei.from_wei(
                ContractERC20OnGnosisChain(
                    address=Web3.to_checksum_address(token)
                ).balanceOf(owner, web3=web3)
            )
            for token in self.wrapped_tokens
        ]

    @property
    def is_binary(self) -> bool:
        # 3 because Seer has also third, `Invalid` outcome.
        return len(self.outcomes) == 3

    @property
    def collateral_token_contract_address_checksummed(self) -> ChecksumAddress:
        return Web3.to_checksum_address(self.collateral_token)

    @property
    def close_time(self) -> DatetimeUTC:
        return DatetimeUTC.to_datetime_utc(self.opening_ts)

    @property
    def created_time(self) -> DatetimeUTC:
        return DatetimeUTC.to_datetime_utc(self.block_timestamp)

    @property
    def url(self) -> str:
        chain_id = RPCConfig().chain_id
        return urljoin(SEER_BASE_URL, f"markets/{chain_id}/{self.id.hex()}")


class RedeemParams(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    market: ChecksumAddress
    outcome_indices: list[int] = Field(alias="outcomeIndexes")
    amounts: list[OutcomeWei]


class ExactInputSingleParams(BaseModel):
    # from https://gnosisscan.io/address/0xffb643e73f280b97809a8b41f7232ab401a04ee1#code
    model_config = ConfigDict(populate_by_name=True)
    token_in: ChecksumAddress = Field(alias="tokenIn")
    token_out: ChecksumAddress = Field(alias="tokenOut")
    recipient: ChecksumAddress
    deadline: int = Field(
        default_factory=lambda: int((utcnow() + timedelta(minutes=10)).timestamp())
    )
    amount_in: Wei = Field(alias="amountIn")
    amount_out_minimum: Wei = Field(alias="amountOutMinimum")
    limit_sqrt_price: Wei = Field(
        alias="limitSqrtPrice", default_factory=lambda: Wei(0)
    )  # 0 for convenience, we also don't expect major price shifts
