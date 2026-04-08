from pydantic import BaseModel, Field

from prediction_market_agent_tooling.gtypes import CollateralToken


class MarketFees(BaseModel):
    # proportion of the bet
    bet_proportion: float = Field(0.0, ge=0.0, lt=1.0)
    # absolute value paid in the currency of the market
    absolute: float = 0.0
    # Price-dependent fee rate for markets using: fee = shares × fee_rate × p × (1 - p)
    trading_fee_rate: float = 0.0

    @staticmethod
    def get_zero_fees(
        bet_proportion: float = 0.0,
        absolute: float = 0.0,
        trading_fee_rate: float = 0.0,
    ) -> "MarketFees":
        return MarketFees(
            bet_proportion=bet_proportion,
            absolute=absolute,
            trading_fee_rate=trading_fee_rate,
        )

    def total_fee_absolute_value(self, bet_amount: float, price: float | None) -> float:
        """
        Returns the total fee in absolute terms, including both proportional and fixed fees.
        """
        if self.trading_fee_rate:
            if price is None:
                raise ValueError(
                    "Price must be provided for price-dependent fee calculation"
                )
            price_dependent_fee = self._price_dependent_fee(bet_amount, price)
            return (
                self.bet_proportion * bet_amount + self.absolute + price_dependent_fee
            )

        return self.bet_proportion * bet_amount + self.absolute

    def total_fee_relative_value(self, bet_amount: float, price: float | None) -> float:
        """
        Returns the total fee relative to the bet amount, including both proportional and fixed fees.
        """
        if bet_amount == 0:
            return 0.0
        total_fee = self.total_fee_absolute_value(bet_amount=bet_amount, price=price)
        return total_fee / bet_amount

    def get_after_fees(
        self, bet_amount: CollateralToken, price: float | None
    ) -> CollateralToken:
        return bet_amount - CollateralToken(
            self.total_fee_absolute_value(bet_amount=bet_amount.value, price=price)
        )

    def _price_dependent_fee(self, collateral_amount: float, price: float) -> float:
        """Compute exact fee for a BUY order on markets with price-dependent fees.

        Fee formula: fee = shares × fee_rate × p × (1 - p)
        For a BUY at price p, you get (collateral_amount / p) shares.
        So: fee = (collateral_amount / p) × fee_rate × p × (1 - p)
                = collateral_amount × fee_rate × (1 - p)

        Returns fee in collateral currency.
        """
        if not self.trading_fee_rate:
            raise ValueError(
                "trading_fee_rate must be set for price-dependent fee calculation"
            )
        return collateral_amount * self.trading_fee_rate * (1 - price)
