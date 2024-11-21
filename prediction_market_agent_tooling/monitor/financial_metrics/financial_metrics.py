import numpy as np
import pandas as pd

from prediction_market_agent_tooling.markets.data_models import (
    SharpeOutput,
    SimulatedBetDetail,
)


class SharpeRatioCalculator:
    def __init__(
        self, details: list[SimulatedBetDetail], risk_free_rate: float = 0.0
    ) -> None:
        self.details = details
        self.df = pd.DataFrame([d.model_dump() for d in self.details])
        self.risk_free_rate = risk_free_rate

    def __has_df_valid_columns_else_exception(
        self, required_columns: list[str]
    ) -> None:
        if not set(required_columns).issubset(self.df.columns):
            raise ValueError("Dataframe doesn't contain all the required columns.")

    def prepare_wallet_daily_balance_df(
        self, timestamp_col_name: str, profit_col_name: str
    ) -> pd.DataFrame:
        self.__has_df_valid_columns_else_exception(
            [timestamp_col_name, profit_col_name]
        )
        df = self.df.copy()
        df[timestamp_col_name] = pd.to_datetime(df[timestamp_col_name])
        df.sort_values(timestamp_col_name, ascending=True, inplace=True)

        df["profit_cumsum"] = df[profit_col_name].cumsum()
        df["profit_cumsum"] = df["profit_cumsum"] + 50

        df = df.drop_duplicates(subset=timestamp_col_name, keep="last")
        df.set_index(timestamp_col_name, inplace=True)
        # We generate a new Dataframe with daily wallet balances, derived by the final wallet balance
        # from the previous day.
        wallet_balance_daily_df = df[["profit_cumsum"]].resample("D").ffill()
        wallet_balance_daily_df.dropna(inplace=True)
        wallet_balance_daily_df["returns"] = wallet_balance_daily_df[
            "profit_cumsum"
        ].pct_change()
        return wallet_balance_daily_df

    def calculate_annual_sharpe_ratio(
        self, timestamp_col_name: str = "timestamp", profit_col_name: str = "sim_profit"
    ) -> SharpeOutput:
        wallet_daily_balance_df = self.prepare_wallet_daily_balance_df(
            timestamp_col_name=timestamp_col_name, profit_col_name=profit_col_name
        )

        daily_volatility = wallet_daily_balance_df["returns"].std()
        annualized_volatility = daily_volatility * np.sqrt(365)
        mean_daily_return = wallet_daily_balance_df["returns"].mean()
        daily_sharpe_ratio = (
            mean_daily_return - self.risk_free_rate
        ) / daily_volatility
        annualized_sharpe_ratio = daily_sharpe_ratio * np.sqrt(365)
        return SharpeOutput(
            annualized_volatility=annualized_volatility,
            mean_daily_return=mean_daily_return,
            annualized_sharpe_ratio=annualized_sharpe_ratio,
        )
