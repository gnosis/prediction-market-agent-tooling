import typing as t
from datetime import datetime
from decimal import Decimal

from eth_typing import ChecksumAddress, HexAddress
from pydantic import BaseModel
from web3 import Web3

from prediction_market_agent_tooling.gtypes import (
    USD,
    OmenOutcomeToken,
    Probability,
    Wei,
    xDai,
)
from prediction_market_agent_tooling.markets.data_models import (
    Currency,
    ProfitAmount,
    ResolvedBet,
)


class OmenMarket(BaseModel):
    """
    https://aiomen.eth.limo
    """

    id: HexAddress
    title: str
    collateralVolume: Wei
    usdVolume: USD
    collateralToken: HexAddress
    outcomes: list[str]
    outcomeTokenAmounts: list[OmenOutcomeToken]
    outcomeTokenMarginalPrices: t.Optional[list[xDai]]
    fee: t.Optional[Wei]

    @property
    def market_maker_contract_address(self) -> HexAddress:
        return self.id

    @property
    def market_maker_contract_address_checksummed(self) -> ChecksumAddress:
        return Web3.to_checksum_address(self.market_maker_contract_address)

    @property
    def collateral_token_contract_address(self) -> HexAddress:
        return self.collateralToken

    @property
    def collateral_token_contract_address_checksummed(self) -> ChecksumAddress:
        return Web3.to_checksum_address(self.collateral_token_contract_address)

    @property
    def outcomeTokenProbabilities(self) -> t.Optional[list[Probability]]:
        return (
            [Probability(float(x)) for x in self.outcomeTokenMarginalPrices]
            if self.outcomeTokenMarginalPrices is not None
            else None
        )

    def get_outcome_str(self, outcome_index: int) -> str:
        n_outcomes = len(self.outcomes)
        if outcome_index >= n_outcomes:
            raise ValueError(
                f"Outcome index `{outcome_index}` not valid. There are only "
                f"`{n_outcomes}` outcomes."
            )
        else:
            return self.outcomes[outcome_index]

    def __repr__(self) -> str:
        return f"Omen's market: {self.title}"


class OmenBet(BaseModel):
    shares: Decimal

    def to_generic_resolved_bet(self) -> ResolvedBet:
        return ResolvedBet(
            market_outcome=True,
            resolved_time=datetime.now(),
            profit=ProfitAmount(amount=0.01, currency=Currency.xDai),
        )
