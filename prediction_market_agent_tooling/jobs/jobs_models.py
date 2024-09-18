from datetime import datetime

from pydantic import BaseModel
from web3 import Web3

from prediction_market_agent_tooling.deploy.betting_strategy import (
    Currency,
    KellyBettingStrategy,
    ProbabilisticAnswer,
    TradeType,
)
from prediction_market_agent_tooling.gtypes import Probability, xDai, xdai_type
from prediction_market_agent_tooling.markets.omen.data_models import (
    get_bet_outcome,
    get_outcome_index,
)
from prediction_market_agent_tooling.markets.omen.omen import (
    OmenAgentMarket,
    OmenMarket,
)
from prediction_market_agent_tooling.tools.web3_utils import wei_to_xdai, xdai_to_wei


class OmenJob(BaseModel):
    description: str
    reward: xDai
    deadline: datetime

    @staticmethod
    def from_omen_market(market: OmenMarket, max_bond: xDai) -> "OmenJob":
        return OmenJob(
            description=market.question_title,
            reward=compute_job_reward(market, max_bond),
            deadline=market.close_time,
        )


def compute_job_reward(
    market: OmenMarket, max_bond: xDai, web3: Web3 | None = None
) -> xDai:
    agent_market = OmenAgentMarket.from_data_model(market)
    market_contract = agent_market.get_contract()

    # Because jobs are powered by prediction markets, potentional reward depends on job's liquidity and our will to bond (bet) our xDai into our job completion.
    required_trades = KellyBettingStrategy(max_bet_amount=max_bond).calculate_trades(
        existing_position=None,
        # We assume that we finish the job and so the probability of the market happening will be 100%.
        answer=ProbabilisticAnswer(p_yes=Probability(1.0), confidence=1.0),
        market=agent_market,
    )

    assert (
        len(required_trades) == 1
    ), f"Shouldn't process same job twice: {required_trades}"
    trade = required_trades[0]
    assert trade.trade_type == TradeType.BUY, "Should only buy on job markets."
    assert trade.outcome, "Should buy only YES on job markets."
    assert (
        trade.amount.currency == Currency.xDai
    ), "Should work only on real-money markets."

    bet_amount = xdai_type(trade.amount.amount)

    outcome_tokens = market_contract.calcBuyAmount(
        investment_amount=xdai_to_wei(bet_amount),
        outcome_index=market.yes_index if trade.outcome else market.no_index,
        web3=web3,
    )

    reward = xdai_type(wei_to_xdai(outcome_tokens) - bet_amount)

    return reward
