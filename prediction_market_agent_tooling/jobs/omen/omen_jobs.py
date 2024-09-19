import typing as t
from datetime import datetime

from web3 import Web3

from prediction_market_agent_tooling.deploy.betting_strategy import (
    Currency,
    KellyBettingStrategy,
    ProbabilisticAnswer,
    TradeType,
)
from prediction_market_agent_tooling.gtypes import Probability, xdai_type
from prediction_market_agent_tooling.jobs.jobs_models import JobAgentMarket
from prediction_market_agent_tooling.markets.omen.omen import (
    OmenAgentMarket,
    OmenMarket,
)
from prediction_market_agent_tooling.markets.omen.omen_subgraph_handler import (
    FilterBy,
    OmenSubgraphHandler,
    SortBy,
)
from prediction_market_agent_tooling.tools.web3_utils import wei_to_xdai, xdai_to_wei


class OmenJobAgentMarket(OmenAgentMarket, JobAgentMarket):
    CATEGORY = "jobs"

    @property
    def job(self) -> str:
        """Omen market's have only question, so that's where the job description is."""
        return self.question

    @property
    def deadline(self) -> datetime:
        return self.close_time

    def get_reward(self, max_bond: float) -> float:
        return compute_job_reward(self, max_bond)

    @classmethod
    def get_jobs(
        cls, limit: int | None, filter_by: FilterBy, sort_by: SortBy
    ) -> t.Sequence["OmenJobAgentMarket"]:
        markets = OmenSubgraphHandler().get_omen_binary_markets_simple(
            limit=limit,
            filter_by=filter_by,
            sort_by=sort_by,
            category=cls.CATEGORY,
        )
        return [OmenJobAgentMarket.from_omen_market(market) for market in markets]

    @staticmethod
    def from_omen_market(market: OmenMarket) -> "OmenJobAgentMarket":
        return OmenJobAgentMarket.from_omen_agent_market(
            OmenAgentMarket.from_data_model(market)
        )

    @staticmethod
    def from_omen_agent_market(market: OmenAgentMarket) -> "OmenJobAgentMarket":
        return OmenJobAgentMarket(
            id=market.id,
            question=market.question,
            description=market.description,
            outcomes=market.outcomes,
            outcome_token_pool=market.outcome_token_pool,
            resolution=market.resolution,
            created_time=market.created_time,
            close_time=market.close_time,
            current_p_yes=market.current_p_yes,
            url=market.url,
            volume=market.volume,
            creator=market.creator,
            collateral_token_contract_address_checksummed=market.collateral_token_contract_address_checksummed,
            market_maker_contract_address_checksummed=market.market_maker_contract_address_checksummed,
            condition=market.condition,
            finalized_time=market.finalized_time,
            fee=market.fee,
        )


def compute_job_reward(
    market: OmenAgentMarket, max_bond: float, web3: Web3 | None = None
) -> float:
    market_contract = market.get_contract()

    # Because jobs are powered by prediction markets, potentional reward depends on job's liquidity and our will to bond (bet) our xDai into our job completion.
    required_trades = KellyBettingStrategy(max_bet_amount=max_bond).calculate_trades(
        existing_position=None,
        # We assume that we finish the job and so the probability of the market happening will be 100%.
        answer=ProbabilisticAnswer(p_yes=Probability(1.0), confidence=1.0),
        market=market,
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

    # TODO: Use after merged https://github.com/gnosis/prediction-market-agent-tooling/pull/415.
    outcome_tokens = market_contract.calcBuyAmount(
        investment_amount=xdai_to_wei(bet_amount),
        outcome_index=market.yes_index if trade.outcome else market.no_index,
        web3=web3,
    )

    reward = xdai_type(wei_to_xdai(outcome_tokens) - bet_amount)

    return reward
