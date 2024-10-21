import getpass
import inspect
import os
import tempfile
import time
import typing as t
from datetime import timedelta
from enum import Enum
from functools import cached_property

from pydantic import BaseModel, BeforeValidator, computed_field
from typing_extensions import Annotated
from web3 import Web3
from web3.constants import HASH_ZERO

from prediction_market_agent_tooling.config import APIKeys
from prediction_market_agent_tooling.deploy.betting_strategy import (
    BettingStrategy,
    MaxAccuracyBettingStrategy,
    TradeType,
)
from prediction_market_agent_tooling.deploy.constants import (
    MARKET_TYPE_KEY,
    REPOSITORY_KEY,
)
from prediction_market_agent_tooling.deploy.gcp.deploy import (
    deploy_to_gcp,
    run_deployed_gcp_function,
    schedule_deployed_gcp_function,
)
from prediction_market_agent_tooling.deploy.gcp.utils import (
    gcp_function_is_active,
    gcp_resolve_api_keys_secrets,
)
from prediction_market_agent_tooling.gtypes import HexStr, xDai, xdai_type
from prediction_market_agent_tooling.loggers import logger
from prediction_market_agent_tooling.markets.agent_market import (
    AgentMarket,
    FilterBy,
    SortBy,
)
from prediction_market_agent_tooling.markets.data_models import (
    PlacedTrade,
    Position,
    ProbabilisticAnswer,
    Trade,
)
from prediction_market_agent_tooling.markets.markets import (
    MarketType,
    have_bet_on_market_since,
)
from prediction_market_agent_tooling.markets.omen.data_models import (
    ContractPrediction,
    IPFSAgentResult,
)
from prediction_market_agent_tooling.markets.omen.omen import (
    is_minimum_required_balance,
    redeem_from_all_user_positions,
    withdraw_wxdai_to_xdai_to_keep_balance,
)
from prediction_market_agent_tooling.markets.omen.omen_contracts import (
    OmenAgentResultMappingContract,
)
from prediction_market_agent_tooling.monitor.monitor_app import (
    MARKET_TYPE_TO_DEPLOYED_AGENT,
)
from prediction_market_agent_tooling.tools.hexbytes_custom import HexBytes
from prediction_market_agent_tooling.tools.ipfs.ipfs_handler import IPFSHandler
from prediction_market_agent_tooling.tools.is_invalid import is_invalid
from prediction_market_agent_tooling.tools.is_predictable import is_predictable_binary
from prediction_market_agent_tooling.tools.langfuse_ import langfuse_context, observe
from prediction_market_agent_tooling.tools.utils import DatetimeUTC, utcnow
from prediction_market_agent_tooling.tools.web3_utils import ipfscidv0_to_byte32

MAX_AVAILABLE_MARKETS = 20
TRADER_TAG = "trader"


def to_boolean_outcome(value: str | bool) -> bool:
    if isinstance(value, bool):
        return value

    elif isinstance(value, str):
        value = value.lower().strip()

        if value in {"true", "yes", "y", "1"}:
            return True

        elif value in {"false", "no", "n", "0"}:
            return False

        else:
            raise ValueError(f"Expected a boolean string, but got {value}")

    else:
        raise ValueError(f"Expected a boolean or a string, but got {value}")


def initialize_langfuse(enable_langfuse: bool) -> None:
    # Configure Langfuse singleton with our APIKeys.
    # If langfuse is disabled, it will just ignore all the calls, so no need to do if-else around the code.
    keys = APIKeys()
    if enable_langfuse:
        langfuse_context.configure(
            public_key=keys.langfuse_public_key,
            secret_key=keys.langfuse_secret_key.get_secret_value(),
            host=keys.langfuse_host,
            enabled=enable_langfuse,
        )
    else:
        langfuse_context.configure(enabled=enable_langfuse)


Decision = Annotated[bool, BeforeValidator(to_boolean_outcome)]


class CantPayForGasError(ValueError):
    pass


class OutOfFundsError(ValueError):
    pass


class ProcessedMarket(BaseModel):
    answer: ProbabilisticAnswer
    trades: list[PlacedTrade]


class AnsweredEnum(str, Enum):
    ANSWERED = "answered"
    NOT_ANSWERED = "not_answered"


class DeployableAgent:
    def __init__(
        self,
        enable_langfuse: bool = APIKeys().default_enable_langfuse,
    ) -> None:
        self.start_time = utcnow()
        self.enable_langfuse = enable_langfuse
        self.initialize_langfuse()
        self.load()

    def initialize_langfuse(self) -> None:
        initialize_langfuse(self.enable_langfuse)

    def langfuse_update_current_trace(
        self,
        name: str | None = None,
        input: t.Any | None = None,
        output: t.Any | None = None,
        user_id: str | None = None,
        session_id: str | None = None,
        version: str | None = None,
        release: str | None = None,
        metadata: t.Any | None = None,
        tags: list[str] | None = None,
        public: bool | None = None,
    ) -> None:
        """
        Provide some useful default arguments when updating the current trace in our agents.
        """
        langfuse_context.update_current_trace(
            name=name,
            input=input,
            output=output,
            user_id=user_id or getpass.getuser(),
            session_id=session_id
            or self.session_id,  # All traces within a single run execution will be grouped under a single session.
            version=version
            or APIKeys().LANGFUSE_DEPLOYMENT_VERSION,  # Optionally, mark the current deployment with version (e.g. add git commit hash during docker building).
            release=release,
            metadata=metadata,
            tags=tags,
            public=public,
        )

    @computed_field  # type: ignore[prop-decorator] # Mypy issue: https://github.com/python/mypy/issues/14461
    @cached_property
    def session_id(self) -> str:
        # Each agent should be an unique class.
        return f"{self.__class__.__name__} - {self.start_time.strftime('%Y-%m-%d %H:%M:%S')}"

    def __init_subclass__(cls, **kwargs: t.Any) -> None:
        if "DeployableAgent" not in str(
            cls.__init__
        ) and "DeployableTraderAgent" not in str(cls.__init__):
            raise TypeError(
                "Cannot override __init__ method of deployable agent class, please override the `load` method to set up the agent."
            )

    def load(self) -> None:
        pass

    def deploy_local(
        self,
        market_type: MarketType,
        sleep_time: float,
        timeout: float,
    ) -> None:
        start_time = time.time()
        while True:
            self.run(market_type=market_type)
            time.sleep(sleep_time)
            if time.time() - start_time > timeout:
                break

    def deploy_gcp(
        self,
        repository: str,
        market_type: MarketType,
        api_keys: APIKeys,
        memory: int,
        labels: dict[str, str] | None = None,
        env_vars: dict[str, str] | None = None,
        secrets: dict[str, str] | None = None,
        cron_schedule: str | None = None,
        gcp_fname: str | None = None,
        start_time: DatetimeUTC | None = None,
        timeout: int = 180,
    ) -> None:
        path_to_agent_file = os.path.relpath(inspect.getfile(self.__class__))

        entrypoint_function_name = "main"
        entrypoint_template = f"""
from {path_to_agent_file.replace("/", ".").replace(".py", "")} import *
import functions_framework
from prediction_market_agent_tooling.markets.markets import MarketType

@functions_framework.http
def {entrypoint_function_name}(request) -> str:
    {self.__class__.__name__}().run(market_type={market_type.__class__.__name__}.{market_type.name})
    return "Success"
"""

        gcp_fname = gcp_fname or self.get_gcloud_fname(market_type)

        # For labels, only hyphens (-), underscores (_), lowercase characters, and numbers are allowed in values.
        labels = (labels or {}) | {
            MARKET_TYPE_KEY: market_type.value,
        }
        env_vars = (env_vars or {}) | {
            REPOSITORY_KEY: repository,
        }
        secrets = secrets or {}

        env_vars |= api_keys.model_dump_public()
        secrets |= api_keys.model_dump_secrets()

        monitor_agent = MARKET_TYPE_TO_DEPLOYED_AGENT[market_type].from_api_keys(
            name=gcp_fname,
            start_time=start_time or utcnow(),
            api_keys=gcp_resolve_api_keys_secrets(api_keys),
        )
        env_vars |= monitor_agent.model_dump_prefixed()

        with tempfile.NamedTemporaryFile(mode="w", suffix=".py") as f:
            f.write(entrypoint_template)
            f.flush()

            fname = deploy_to_gcp(
                gcp_fname=gcp_fname,
                requirements_file=None,
                extra_deps=[repository],
                function_file=f.name,
                labels=labels,
                env_vars=env_vars,
                secrets=secrets,
                memory=memory,
                entrypoint_function_name=entrypoint_function_name,
                timeout=timeout,
            )

        # Check that the function is deployed
        if not gcp_function_is_active(fname):
            raise RuntimeError("Failed to deploy the function")

        # Run the function
        response = run_deployed_gcp_function(fname)
        if not response.ok:
            raise RuntimeError("Failed to run the deployed function")

        # Schedule the function
        if cron_schedule:
            schedule_deployed_gcp_function(fname, cron_schedule=cron_schedule)

    def run(self, market_type: MarketType) -> None:
        raise NotImplementedError("This method must be implemented by the subclass.")

    def get_gcloud_fname(self, market_type: MarketType) -> str:
        return f"{self.__class__.__name__.lower()}-{market_type}-{utcnow().strftime('%Y-%m-%d--%H-%M-%S')}"


class DeployableTraderAgent(DeployableAgent):
    bet_on_n_markets_per_run: int = 1
    min_required_balance_to_operate: xDai | None = xdai_type(1)
    min_balance_to_keep_in_native_currency: xDai | None = xdai_type(0.1)
    allow_invalid_questions: bool = False
    same_market_bet_interval: timedelta = timedelta(hours=24)

    def __init__(
        self,
        enable_langfuse: bool = APIKeys().default_enable_langfuse,
        place_bet: bool = True,
    ) -> None:
        super().__init__(enable_langfuse=enable_langfuse)
        self.place_bet = place_bet

    def get_betting_strategy(self, market: AgentMarket) -> BettingStrategy:
        user_id = market.get_user_id(api_keys=APIKeys())

        total_amount = market.get_tiny_bet_amount().amount
        if existing_position := market.get_position(user_id=user_id):
            total_amount += existing_position.total_amount.amount

        return MaxAccuracyBettingStrategy(bet_amount=total_amount)

    def initialize_langfuse(self) -> None:
        super().initialize_langfuse()
        # Auto-observe all the methods where it makes sense, so that subclassses don't need to do it manually.
        self.have_bet_on_market_since = observe()(self.have_bet_on_market_since)  # type: ignore[method-assign]
        self.verify_market = observe()(self.verify_market)  # type: ignore[method-assign]
        self.answer_binary_market = observe()(self.answer_binary_market)  # type: ignore[method-assign]
        self.process_market = observe()(self.process_market)  # type: ignore[method-assign]
        self.build_trades = observe()(self.build_trades)  # type: ignore[method-assign]

    def update_langfuse_trace_by_market(
        self, market_type: MarketType, market: AgentMarket
    ) -> None:
        self.langfuse_update_current_trace(
            # UI allows to do filtering by these.
            metadata={
                "agent_class": self.__class__.__name__,
                "market_id": market.id,
                "market_question": market.question,
                "market_outcomes": market.outcomes,
            },
        )

    def update_langfuse_trace_by_processed_market(
        self, market_type: MarketType, processed_market: ProcessedMarket | None
    ) -> None:
        self.langfuse_update_current_trace(
            tags=[
                TRADER_TAG,
                (
                    AnsweredEnum.ANSWERED
                    if processed_market is not None
                    else AnsweredEnum.NOT_ANSWERED
                ),
                market_type.value,
            ]
        )

    @property
    def agent_name(self) -> str:
        return self.__class__.__name__

    def check_min_required_balance_to_operate(
        self,
        market_type: MarketType,
        check_for_gas: bool = True,
        check_for_trades: bool = True,
    ) -> None:
        api_keys = APIKeys()
        if (
            market_type == MarketType.OMEN
            and check_for_gas
            and not is_minimum_required_balance(
                api_keys.public_key,
                min_required_balance=xdai_type(0.001),
                sum_wxdai=False,
            )
        ):
            raise CantPayForGasError(
                f"{api_keys.public_key=} doesn't have enough xDai to pay for gas."
            )
        if self.min_required_balance_to_operate is None:
            return
        if (
            market_type == MarketType.OMEN
            and check_for_trades
            and not is_minimum_required_balance(
                api_keys.bet_from_address,
                min_required_balance=self.min_required_balance_to_operate,
            )
        ):
            raise OutOfFundsError(
                f"Minimum required balance {self.min_required_balance_to_operate} "
                f"for agent with address {api_keys.bet_from_address=} is not met."
            )

    def have_bet_on_market_since(self, market: AgentMarket, since: timedelta) -> bool:
        return have_bet_on_market_since(keys=APIKeys(), market=market, since=since)

    def verify_market(self, market_type: MarketType, market: AgentMarket) -> bool:
        """
        Subclasses can implement their own logic instead of this one, or on top of this one.
        By default, it allows only markets where user didn't bet recently and it's a reasonable question.
        """
        if self.have_bet_on_market_since(market, since=self.same_market_bet_interval):
            return False

        # Manifold allows to bet only on markets with probability between 1 and 99.
        if market_type == MarketType.MANIFOLD and not (1 < market.current_p_yes < 99):
            return False

        # Do as a last check, as it uses paid OpenAI API.
        if not is_predictable_binary(market.question):
            return False

        if not self.allow_invalid_questions and is_invalid(market.question):
            return False

        return True

    def answer_binary_market(self, market: AgentMarket) -> ProbabilisticAnswer | None:
        """
        Answer the binary market. This method must be implemented by the subclass.
        """
        raise NotImplementedError("This method must be implemented by the subclass")

    def get_markets(
        self,
        market_type: MarketType,
        limit: int = MAX_AVAILABLE_MARKETS,
        sort_by: SortBy = SortBy.CLOSING_SOONEST,
        filter_by: FilterBy = FilterBy.OPEN,
    ) -> t.Sequence[AgentMarket]:
        cls = market_type.market_class
        # Fetch the soonest closing markets to choose from
        available_markets = cls.get_binary_markets(
            limit=limit, sort_by=sort_by, filter_by=filter_by
        )
        return available_markets

    def build_trades(
        self,
        market: AgentMarket,
        answer: ProbabilisticAnswer,
        existing_position: Position | None,
    ) -> list[Trade]:
        strategy = self.get_betting_strategy(market=market)
        trades = strategy.calculate_trades(existing_position, answer, market)
        BettingStrategy.assert_trades_currency_match_markets(market, trades)
        return trades

    def before_process_market(
        self, market_type: MarketType, market: AgentMarket
    ) -> None:
        self.update_langfuse_trace_by_market(market_type, market)

    def process_market(
        self,
        market_type: MarketType,
        market: AgentMarket,
        verify_market: bool = True,
    ) -> ProcessedMarket | None:
        logger.info(f"Processing market {market.question=} from {market.url=}.")

        self.before_process_market(market_type, market)

        if verify_market and not self.verify_market(market_type, market):
            logger.info(f"Market '{market.question}' doesn't meet the criteria.")
            self.update_langfuse_trace_by_processed_market(market_type, None)
            return None

        answer = self.answer_binary_market(market)

        if answer is None:
            logger.info(f"No answer for market '{market.question}'.")
            self.update_langfuse_trace_by_processed_market(market_type, None)
            return None

        existing_position = market.get_position(user_id=APIKeys().bet_from_address)
        trades = self.build_trades(
            market=market,
            answer=answer,
            existing_position=existing_position,
        )

        placed_trades = []
        if self.place_bet:
            for trade in trades:
                logger.info(f"Executing trade {trade} on market {market.id}")

                match trade.trade_type:
                    case TradeType.BUY:
                        id = market.buy_tokens(
                            outcome=trade.outcome, amount=trade.amount
                        )
                    case TradeType.SELL:
                        id = market.sell_tokens(
                            outcome=trade.outcome, amount=trade.amount
                        )
                    case _:
                        raise ValueError(f"Unexpected trade type {trade.trade_type}.")
                placed_trades.append(PlacedTrade.from_trade(trade, id))

        processed_market = ProcessedMarket(answer=answer, trades=placed_trades)
        self.update_langfuse_trace_by_processed_market(market_type, processed_market)

        self.after_process_market(
            market_type, market, processed_market=processed_market
        )

        logger.info(f"Processed market {market.question=} from {market.url=}.")
        return processed_market

    def after_process_market(
        self,
        market_type: MarketType,
        market: AgentMarket,
        processed_market: ProcessedMarket,
    ) -> None:
        if market_type != MarketType.OMEN:
            logger.info(
                f"Skipping after_process_market since market_type {market_type} != OMEN"
            )
            return
        keys = APIKeys()
        self.store_prediction(
            market_id=market.id, processed_market=processed_market, keys=keys
        )

    def store_prediction(
        self, market_id: str, processed_market: ProcessedMarket, keys: APIKeys
    ) -> None:
        reasoning = (
            processed_market.answer.reasoning
            if processed_market.answer.reasoning
            else ""
        )

        ipfs_hash_decoded = HexBytes(HASH_ZERO)
        if keys.enable_ipfs_upload:
            logger.info("Storing prediction on IPFS.")
            ipfs_hash = IPFSHandler(keys).store_agent_result(
                IPFSAgentResult(reasoning=reasoning, model=self.model)
            )
            ipfs_hash_decoded = ipfscidv0_to_byte32(ipfs_hash)

        tx_hashes = [
            HexBytes(HexStr(i.id)) for i in processed_market.trades if i.id is not None
        ]
        prediction = ContractPrediction(
            publisher=keys.public_key,
            ipfs_hash=ipfs_hash_decoded,
            tx_hashes=tx_hashes,
            estimated_probability_bps=int(processed_market.answer.p_yes * 10000),
        )
        tx_receipt = OmenAgentResultMappingContract().add_prediction(
            api_keys=keys,
            market_address=Web3.to_checksum_address(market_id),
            prediction=prediction,
        )
        logger.info(
            f"Added prediction to market {market_id}. - receipt {tx_receipt['transactionHash'].hex()}."
        )

    def before_process_markets(self, market_type: MarketType) -> None:
        """
        Executes actions that occur before bets are placed.
        """
        api_keys = APIKeys()
        if market_type == MarketType.OMEN:
            # First, check if we have enough xDai to pay for gas, there is no way of doing anything without it.
            self.check_min_required_balance_to_operate(
                market_type, check_for_trades=False
            )
            # Omen is specific, because the user (agent) needs to manually withdraw winnings from the market.
            redeem_from_all_user_positions(api_keys)
            # After redeeming, check if we have enough xDai to pay for gas and place bets.
            self.check_min_required_balance_to_operate(market_type)
            # Exchange wxdai back to xdai if the balance is getting low, so we can keep paying for fees.
            if self.min_balance_to_keep_in_native_currency is not None:
                withdraw_wxdai_to_xdai_to_keep_balance(
                    api_keys,
                    min_required_balance=self.min_balance_to_keep_in_native_currency,
                    withdraw_multiplier=2,
                )

    def process_markets(self, market_type: MarketType) -> None:
        """
        Processes bets placed by agents on a given market.
        """
        logger.info("Start processing of markets.")
        available_markets = self.get_markets(market_type)
        logger.info(
            f"Fetched {len(available_markets)=} markets to process, going to process {self.bet_on_n_markets_per_run=}."
        )
        processed = 0

        for market in available_markets:
            # We need to check it again before each market bet, as the balance might have changed.
            self.check_min_required_balance_to_operate(market_type)

            processed_market = self.process_market(market_type, market)

            if processed_market is not None:
                processed += 1

            if processed == self.bet_on_n_markets_per_run:
                break

        logger.info("All markets processed.")

    def after_process_markets(self, market_type: MarketType) -> None:
        pass

    def run(self, market_type: MarketType) -> None:
        self.before_process_markets(market_type)
        self.process_markets(market_type)
        self.after_process_markets(market_type)
