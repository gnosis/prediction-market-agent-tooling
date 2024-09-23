import typing as t
from datetime import datetime

from web3 import Web3

from prediction_market_agent_tooling.deploy.betting_strategy import (
    Currency,
    KellyBettingStrategy,
    ProbabilisticAnswer,
    StaticAmount,
    TradeType,
)
from prediction_market_agent_tooling.gtypes import Probability
from prediction_market_agent_tooling.jobs.jobs_models import JobAgentMarket
from prediction_market_agent_tooling.markets.omen.omen import (
    BetAmount,
    OmenAgentMarket,
    OmenMarket,
)
from prediction_market_agent_tooling.markets.omen.omen_subgraph_handler import (
    FilterBy,
    OmenSubgraphHandler,
    SortBy,
)


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
    # Because jobs are powered by prediction markets, potentional reward depends on job's liquidity and our will to bond (bet) our xDai into our job completion.
    strategy = KellyBettingStrategy(max_bet_amount=StaticAmount(amount=max_bond))
    required_trades = strategy.calculate_trades(
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

    reward = (
        market.get_buy_token_amount(
            bet_amount=BetAmount(
                amount=trade.amount.amount, currency=trade.amount.currency
            ),
            direction=trade.outcome,
        ).amount
        - trade.amount.amount
    )

    return reward
