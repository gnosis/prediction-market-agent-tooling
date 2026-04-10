import json
import time
import typing as t
from collections import defaultdict
from datetime import timedelta
from enum import Enum
from pathlib import Path

from pydantic import BaseModel
from web3 import Web3

from prediction_market_agent_tooling.config import APIKeys
from prediction_market_agent_tooling.gtypes import (
    USD,
    ChecksumAddress,
    OutcomeStr,
    OutcomeToken,
    VerifiedChecksumAddress,
)
from prediction_market_agent_tooling.loggers import logger
from prediction_market_agent_tooling.markets.data_models import Resolution
from prediction_market_agent_tooling.markets.polymarket.api import (
    get_polymarkets_with_pagination,
    get_trades_for_market,
    get_user_trades,
)
from prediction_market_agent_tooling.markets.polymarket.data_models import (
    POLYMARKET_FALSE_OUTCOME,
    POLYMARKET_TRUE_OUTCOME,
    PolymarketSideEnum,
    PolymarketTradeResponse,
)
from prediction_market_agent_tooling.markets.polymarket.polymarket import (
    PolymarketAgentMarket,
)
from prediction_market_agent_tooling.markets.polymarket.polymarket_subgraph_handler import (
    PolymarketSubgraphHandler,
)
from prediction_market_agent_tooling.tools.hexbytes_custom import HexBytes
from prediction_market_agent_tooling.tools.utils import DatetimeUTC, utcnow


class TraderSortBy(str, Enum):
    VOLUME = "volume"
    PNL = "pnl"
    ROI = "roi"
    WIN_RATE = "win_rate"


class TraderProfile(BaseModel):
    address: VerifiedChecksumAddress
    total_volume: USD
    total_pnl: USD
    roi: float
    win_rate: float
    trade_count: int
    resolved_trade_count: int
    markets_traded: int
    name: str


class CopyTraderState(BaseModel):
    replicated_tx_hashes: set[str]
    last_poll_timestamp: DatetimeUTC | None = None

    def save(self, path: str) -> None:
        data = self.model_dump(mode="json")
        # set is not JSON-serializable by default, convert to list
        data["replicated_tx_hashes"] = list(data["replicated_tx_hashes"])
        with open(path, "w") as f:
            json.dump(data, f, indent=2)

    @staticmethod
    def load(path: str) -> "CopyTraderState":
        with open(path) as f:
            data = json.load(f)
        data["replicated_tx_hashes"] = set(data["replicated_tx_hashes"])
        return CopyTraderState.model_validate(data)

    @staticmethod
    def empty() -> "CopyTraderState":
        return CopyTraderState(replicated_tx_hashes=set(), last_poll_timestamp=None)


class ReplicatedTradeResult(BaseModel):
    source_tx_hash: str
    replicated_tx_hash: str | None = None
    condition_id: str
    side: PolymarketSideEnum
    outcome: OutcomeStr
    original_size: float
    replicated_amount: float
    skipped: bool = False
    skip_reason: str | None = None


class PolymarketCopyTrader:
    def __init__(
        self,
        target_address: ChecksumAddress,
        api_keys: APIKeys,
        copy_ratio: float = 1.0,
        min_trade_size: USD = USD(1.0),
        poll_interval_seconds: int = 60,
        state_file_path: str | None = None,
        dry_run: bool = False,
    ) -> None:
        if copy_ratio <= 0:
            raise ValueError(f"copy_ratio must be positive, got {copy_ratio}")

        self.target_address = target_address
        self.api_keys = api_keys
        self.copy_ratio = copy_ratio
        self.min_trade_size = min_trade_size
        self.poll_interval_seconds = poll_interval_seconds
        self.state_file_path = state_file_path
        self.dry_run = dry_run

        if state_file_path and Path(state_file_path).exists():
            self._state = CopyTraderState.load(state_file_path)
        else:
            self._state = CopyTraderState.empty()

    def get_new_trades_since(self, since: DatetimeUTC) -> list[PolymarketTradeResponse]:
        trades = get_user_trades(user_address=self.target_address, after=since)
        new_trades = [
            trade
            for trade in trades
            if trade.transactionHash.to_0x_hex() not in self._state.replicated_tx_hashes
        ]
        new_trades.sort(key=lambda trade: trade.timestamp)
        return new_trades

    @staticmethod
    def _make_result(
        trade: PolymarketTradeResponse,
        replicated_amount: float,
        replicated_tx_hash: str | None = None,
        skipped: bool = False,
        skip_reason: str | None = None,
    ) -> ReplicatedTradeResult:
        return ReplicatedTradeResult(
            source_tx_hash=trade.transactionHash.to_0x_hex(),
            condition_id=trade.conditionId.to_0x_hex(),
            side=trade.side,
            outcome=trade.outcome,
            original_size=trade.size,
            replicated_amount=replicated_amount,
            replicated_tx_hash=replicated_tx_hash,
            skipped=skipped,
            skip_reason=skip_reason,
        )

    def replicate_trade(self, trade: PolymarketTradeResponse) -> ReplicatedTradeResult:
        # Look up market
        try:
            market = PolymarketAgentMarket.get_binary_market(
                trade.conditionId.to_0x_hex()
            )
        except Exception as e:
            logger.warning(
                f"Market lookup failed for condition {trade.conditionId.to_0x_hex()}: {e}"
            )
            return self._make_result(
                trade,
                replicated_amount=0,
                skipped=True,
                skip_reason=f"Market lookup failed: {e}",
            )

        # Check if market is tradeable
        if not market.can_be_traded():
            return self._make_result(
                trade,
                replicated_amount=0,
                skipped=True,
                skip_reason="Market is closed or not tradeable",
            )

        if trade.side == PolymarketSideEnum.BUY:
            return self._replicate_buy(trade, market)
        else:
            return self._replicate_sell(trade, market)

    def _replicate_buy(
        self,
        trade: PolymarketTradeResponse,
        market: PolymarketAgentMarket,
    ) -> ReplicatedTradeResult:
        usd_amount = USD(trade.size * trade.price * self.copy_ratio)

        if usd_amount < self.min_trade_size:
            return self._make_result(
                trade,
                replicated_amount=usd_amount.value,
                skipped=True,
                skip_reason=f"Trade size {usd_amount} below minimum {self.min_trade_size}",
            )

        # Check balance
        balance = PolymarketAgentMarket.get_trade_balance(self.api_keys)
        if balance < usd_amount:
            return self._make_result(
                trade,
                replicated_amount=usd_amount.value,
                skipped=True,
                skip_reason=f"Insufficient balance: {balance} < {usd_amount}",
            )

        if self.dry_run:
            return self._make_result(
                trade,
                replicated_amount=usd_amount.value,
                skipped=True,
                skip_reason="dry_run",
            )

        try:
            tx_hash = market.place_bet(
                outcome=trade.outcome,
                amount=usd_amount,
                auto_deposit=True,
                api_keys=self.api_keys,
            )
        except Exception as e:
            logger.exception(
                f"Buy execution failed for trade {trade.transactionHash.to_0x_hex()}: {e}"
            )
            return self._make_result(
                trade,
                replicated_amount=usd_amount.value,
                skipped=True,
                skip_reason=f"Buy execution failed: {e}",
            )

        self._state.replicated_tx_hashes.add(trade.transactionHash.to_0x_hex())
        return self._make_result(
            trade,
            replicated_tx_hash=tx_hash,
            replicated_amount=usd_amount.value,
        )

    def _replicate_sell(
        self,
        trade: PolymarketTradeResponse,
        market: PolymarketAgentMarket,
    ) -> ReplicatedTradeResult:
        scaled_tokens = OutcomeToken(trade.size * self.copy_ratio)

        # Check we actually hold tokens
        our_balance = market.get_token_balance(
            user_id=self.api_keys.bet_from_address, outcome=trade.outcome
        )
        if our_balance <= OutcomeToken(0):
            return self._make_result(
                trade,
                replicated_amount=0,
                skipped=True,
                skip_reason="No position to sell",
            )

        # Sell the minimum of our balance and the scaled amount
        sell_amount = min(scaled_tokens, our_balance)

        if self.dry_run:
            return self._make_result(
                trade,
                replicated_amount=sell_amount.value,
                skipped=True,
                skip_reason="dry_run",
            )

        try:
            tx_hash = market.sell_tokens(
                outcome=trade.outcome,
                amount=sell_amount,
                api_keys=self.api_keys,
            )
        except Exception as e:
            logger.exception(
                f"Sell execution failed for trade {trade.transactionHash.to_0x_hex()}: {e}"
            )
            return self._make_result(
                trade,
                replicated_amount=sell_amount.value,
                skipped=True,
                skip_reason=f"Sell execution failed: {e}",
            )

        self._state.replicated_tx_hashes.add(trade.transactionHash.to_0x_hex())
        return self._make_result(
            trade,
            replicated_tx_hash=tx_hash,
            replicated_amount=sell_amount.value,
        )

    def run_once(self) -> list[ReplicatedTradeResult]:
        since = self._state.last_poll_timestamp or (utcnow() - timedelta(hours=24))
        new_trades = self.get_new_trades_since(since)
        logger.info(
            f"Copy trader found {len(new_trades)} new trades for {self.target_address}"
        )

        results: list[ReplicatedTradeResult] = []
        for trade in new_trades:
            result = self.replicate_trade(trade)
            results.append(result)
            if result.skipped:
                logger.info(
                    f"Skipped trade {result.source_tx_hash}: {result.skip_reason}"
                )
            else:
                logger.info(
                    f"Replicated trade {result.source_tx_hash} -> {result.replicated_tx_hash}"
                )

        self._state.last_poll_timestamp = utcnow()
        if self.state_file_path:
            self.save_state()

        return results

    def run_loop(self, run_time: float | None = None) -> None:
        start_time = time.time()
        while run_time is None or time.time() - start_time < run_time:
            try:
                self.run_once()
            except Exception:
                logger.exception("Error in copy trading loop iteration")
            time.sleep(self.poll_interval_seconds)

    def save_state(self, path: str | None = None) -> None:
        path = path or self.state_file_path
        if path is None:
            raise ValueError("No state file path provided")
        self._state.save(path)

    def load_state(self, path: str | None = None) -> None:
        path = path or self.state_file_path
        if path is None:
            raise ValueError("No state file path provided")
        self._state = CopyTraderState.load(path)


def discover_top_traders(
    market_count: int = 10,
    trades_per_market: int = 500,
    sort_by: TraderSortBy = TraderSortBy.PNL,
    min_trade_count: int = 5,
) -> list[TraderProfile]:
    # Fetch active markets with high volume
    gamma_items = get_polymarkets_with_pagination(
        limit=market_count,
        active=True,
        closed=False,
    )

    # Collect all trades across markets
    all_trades: list[PolymarketTradeResponse] = []
    condition_ids: set[str] = set()
    for item in gamma_items:
        if item.markets is None:
            continue
        for market in item.markets:
            cid = market.conditionId
            condition_ids.add(cid.to_0x_hex())
            trades = get_trades_for_market(market=cid, limit=trades_per_market)
            all_trades.extend(trades)

    if not all_trades:
        return []

    # Fetch resolution data for all condition IDs
    unique_cids = list({trade.conditionId for trade in all_trades})
    conditions = PolymarketSubgraphHandler().get_conditions(unique_cids)
    condition_dict = {c.id: c for c in conditions}

    binary_outcomes = [
        OutcomeStr(POLYMARKET_TRUE_OUTCOME),
        OutcomeStr(POLYMARKET_FALSE_OUTCOME),
    ]

    # Build resolution map
    resolution_map: dict[str, Resolution] = {}
    for cid_hex in condition_ids:
        cid = HexBytes(cid_hex)
        resolution = PolymarketAgentMarket.build_resolution_from_condition(
            condition_id=cid,
            condition_model_dict=condition_dict,
            outcomes=binary_outcomes,
        )
        if resolution is not None and resolution.outcome is not None:
            resolution_map[cid_hex] = resolution

    # Group trades by trader
    trades_by_trader: dict[str, list[PolymarketTradeResponse]] = defaultdict(list)
    for trade in all_trades:
        trades_by_trader[trade.proxyWallet].append(trade)

    # Calculate metrics per trader
    profiles: list[TraderProfile] = []
    for address, trader_trades in trades_by_trader.items():
        if len(trader_trades) < min_trade_count:
            continue

        total_volume = USD(0)
        total_pnl = USD(0)
        total_cost = USD(0)
        resolved_count = 0
        winning_count = 0
        unique_markets: set[str] = set()

        for trade in trader_trades:
            cost = trade.size * trade.price
            total_volume = USD(total_volume.value + cost)
            unique_markets.add(trade.conditionId.to_0x_hex())

            cid_hex = trade.conditionId.to_0x_hex()
            if cid_hex in resolution_map:
                resolution = resolution_map[cid_hex]
                bet = trade.to_polymarket_bet()
                profit = bet.get_profit(resolution)
                total_pnl = USD(total_pnl.value + profit.value)
                total_cost = USD(total_cost.value + cost)
                resolved_count += 1
                if profit.value > 0:
                    winning_count += 1

        roi = total_pnl.value / total_cost.value if total_cost.value > 0 else 0.0
        win_rate = winning_count / resolved_count if resolved_count > 0 else 0.0

        profiles.append(
            TraderProfile(
                address=Web3.to_checksum_address(address),
                total_volume=total_volume,
                total_pnl=total_pnl,
                roi=roi,
                win_rate=win_rate,
                trade_count=len(trader_trades),
                resolved_trade_count=resolved_count,
                markets_traded=len(unique_markets),
                name=trader_trades[0].name if trader_trades else "",
            )
        )

    # Sort by requested metric
    sort_key: t.Callable[[TraderProfile], float]
    match sort_by:
        case TraderSortBy.VOLUME:
            sort_key = lambda p: p.total_volume.value
        case TraderSortBy.PNL:
            sort_key = lambda p: p.total_pnl.value
        case TraderSortBy.ROI:
            sort_key = lambda p: p.roi
        case TraderSortBy.WIN_RATE:
            sort_key = lambda p: p.win_rate
        case _:
            raise ValueError(f"Unknown sort_by: {sort_by}")

    profiles.sort(key=sort_key, reverse=True)
    return profiles
