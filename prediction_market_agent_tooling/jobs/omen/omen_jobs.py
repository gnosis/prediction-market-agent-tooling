import typing as t

from prediction_market_agent_tooling.config import APIKeys
from prediction_market_agent_tooling.deploy.betting_strategy import (
    Currency,
    KellyBettingStrategy,
    TradeType,
)
from prediction_market_agent_tooling.jobs.jobs_models import JobAgentMarket
from prediction_market_agent_tooling.markets.agent_market import ProcessedTradedMarket
from prediction_market_agent_tooling.markets.data_models import PlacedTrade, Trade
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
from prediction_market_agent_tooling.tools.utils import DatetimeUTC


class OmenJobAgentMarket(OmenAgentMarket, JobAgentMarket):
    CATEGORY = "jobs"

    @property
    def job(self) -> str:
        """Omen market's have only question, so that's where the job description is."""
        return self.question

    @property
    def deadline(self) -> DatetimeUTC:
        return self.close_time

    def get_reward(self, max_bond: float) -> float:
        trade = self.get_job_trade(
            max_bond,
            result="",  # Pass empty result, as we are computing only potential reward at this point.
        )
        reward = (
            self.get_buy_token_amount(
                bet_amount=BetAmount(
                    amount=trade.amount.amount, currency=trade.amount.currency
                ),
                direction=trade.outcome,
            ).amount
            - trade.amount.amount
        )
        return reward

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

    def submit_job_result(self, max_bond: float, result: str) -> ProcessedTradedMarket:
        trade = self.get_job_trade(max_bond, result)
        buy_id = self.buy_tokens(outcome=trade.outcome, amount=trade.amount)

        processed_traded_market = ProcessedTradedMarket(
            answer=self.get_job_answer(result),
            trades=[PlacedTrade.from_trade(trade, id=buy_id)],
        )

        keys = APIKeys()
        self.store_trades(processed_traded_market, keys)

        return processed_traded_market

    def get_job_trade(self, max_bond: float, result: str) -> Trade:
        # Because jobs are powered by prediction markets, potentional reward depends on job's liquidity and our will to bond (bet) our xDai into our job completion.
        strategy = KellyBettingStrategy(max_bet_amount=max_bond)
        required_trades = strategy.calculate_trades(
            existing_position=None,
            answer=self.get_job_answer(result),
            market=self,
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
        return required_trades[0]

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
            fees=market.fees,
        )
