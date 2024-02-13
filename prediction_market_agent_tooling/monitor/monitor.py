import altair as alt
from datetime import datetime
from pydantic import BaseModel
import pandas as pd
import streamlit as st
import typing as t
from zoneinfo import ZoneInfo

from prediction_market_agent_tooling.markets.data_models import ResolvedBet


class DeployedAgent(BaseModel):
    name: str
    start_time: datetime = datetime.now().astimezone(tz=ZoneInfo("UTC"))
    end_time: t.Optional[datetime] = None

    def get_resolved_bets(self) -> list[ResolvedBet]:
        raise NotImplementedError("Subclasses must implement this method.")


def monitor_agent(agent: DeployedAgent) -> None:
    agent_bets = agent.get_resolved_bets()
    bets_info = {
        "Market Question": [bet.market_question for bet in agent_bets],
        "Bet Amount": [bet.amount.amount for bet in agent_bets],
        "Bet Outcome": [bet.outcome for bet in agent_bets],
        "Created Time": [bet.created_time for bet in agent_bets],
        "Resolved Time": [bet.resolved_time for bet in agent_bets],
        "Is Correct": [bet.is_correct for bet in agent_bets],
        "Profit": [bet.profit.amount for bet in agent_bets],
    }
    bets_df = pd.DataFrame(bets_info).sort_values(by="Resolved Time")

    st.set_page_config(layout="wide")
    st.title(f"Monitoring Agent: '{agent.name}'")

    # Metrics
    col1, col2 = st.columns(2)
    col1.metric(label="Number of bets", value=f"{len(agent_bets)}")
    col2.metric(label="% Correct", value=f"{100 * bets_df['Is Correct'].mean():.2f}%")

    # Chart of cumulative profit per day
    profit_info = {
        "Time": bets_df["Resolved Time"],
        "Cumulative Profit": bets_df["Profit"].astype(float),
    }
    profit_df = pd.DataFrame(profit_info)
    profit_df["Date"] = pd.to_datetime(profit_df["Time"].dt.date)
    profit_df = (
        profit_df.groupby("Date")["Cumulative Profit"].sum().cumsum().reset_index()
    )
    profit_df["Cumulative Profit"] = profit_df["Cumulative Profit"].astype(float)
    st.empty()
    st.altair_chart(
        alt.Chart(profit_df)
        .mark_line()
        .encode(
            x=alt.X("Date", axis=alt.Axis(format="%Y-%m-%d"), title=None),
            y=alt.Y("Cumulative Profit", axis=alt.Axis(format=".2f")),
        )
        .interactive(),
        use_container_width=True,
    )

    # Table of resolved bets
    st.empty()
    st.subheader("Resolved Bet History")
    st.table(bets_df)
