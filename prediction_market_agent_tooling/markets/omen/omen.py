from decimal import Decimal

from prediction_market_agent_tooling.config import APIKeys
from prediction_market_agent_tooling.gtypes import ChecksumAddress, xDai
from prediction_market_agent_tooling.markets.agent_market import AgentMarket
from prediction_market_agent_tooling.markets.data_models import BetAmount, Currency
from prediction_market_agent_tooling.markets.omen.api import (
    binary_omen_buy_outcome_tx,
    get_omen_binary_markets,
)
from prediction_market_agent_tooling.markets.omen.data_models import OmenMarket
from prediction_market_agent_tooling.tools.utils import check_not_none


class OmenAgentMarket(AgentMarket):
    """
    Omen's market class that can be used by agents to make predictions.
    """

    currency: Currency = Currency.xDai
    collateral_token_contract_address_checksummed: ChecksumAddress
    market_maker_contract_address_checksummed: ChecksumAddress

    def get_tiny_bet_amount(self) -> BetAmount:
        return BetAmount(amount=Decimal(0.00001), currency=self.currency)

    def place_bet(
        self, outcome: bool, amount: BetAmount, omen_auto_deposit: bool = True
    ) -> None:
        if amount.currency != self.currency:
            raise ValueError(f"Omen bets are made in xDai. Got {amount.currency}.")
        amount_xdai = xDai(amount.amount)
        keys = APIKeys()
        binary_omen_buy_outcome_tx(
            amount=check_not_none(amount_xdai),
            from_address=check_not_none(keys.bet_from_address),
            from_private_key=check_not_none(keys.bet_from_private_key),
            market=self,
            binary_outcome=outcome,
            auto_deposit=omen_auto_deposit,
        )

    @staticmethod
    def from_data_model(model: OmenMarket) -> "OmenAgentMarket":
        return OmenAgentMarket(
            id=model.id,
            question=model.title,
            outcomes=model.outcomes,
            collateral_token_contract_address_checksummed=model.collateral_token_contract_address_checksummed,
            market_maker_contract_address_checksummed=model.market_maker_contract_address_checksummed,
        )

    @staticmethod
    def get_binary_markets(limit: int) -> list[AgentMarket]:
        return [
            OmenAgentMarket.from_data_model(m)
            for m in get_omen_binary_markets(limit=limit)
        ]
