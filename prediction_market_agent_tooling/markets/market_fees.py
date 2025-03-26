from pydantic import BaseModel, Field

from prediction_market_agent_tooling.gtypes import CollateralToken


class MarketFees(BaseModel):
    bet_proportion: float = Field(
        ..., ge=0.0, lt=1.0
    )  # proportion of the bet, from 0 to 1
    absolute: float  # absolute value paid in the currency of the market

    @staticmethod
    def get_zero_fees(
        bet_proportion: float = 0.0,
        absolute: float = 0.0,
    ) -> "MarketFees":
        return MarketFees(
            bet_proportion=bet_proportion,
            absolute=absolute,
        )

    def total_fee_absolute_value(self, bet_amount: float) -> float:
        """
        Returns the total fee in absolute terms, including both proportional and fixed fees.
        """
        return self.bet_proportion * bet_amount + self.absolute

    def total_fee_relative_value(self, bet_amount: float) -> float:
        """
        Returns the total fee relative to the bet amount, including both proportional and fixed fees.
        """
        if bet_amount == 0:
            return 0.0
        total_fee = self.total_fee_absolute_value(bet_amount)
        return total_fee / bet_amount

    def get_after_fees(self, bet_amount: CollateralToken) -> CollateralToken:
        return bet_amount - CollateralToken(
            self.total_fee_absolute_value(bet_amount.value)
        )
