# DeployableTraderAgent Class


The `DeployableTraderAgent` class provides a standardized framework for creating trading agents that interact with prediction markets. It extends the `DeployablePredictionAgent`, adding functionality for placing trades based on market predictions. This allows developers to subclass it to create customized trading strategies.

## Class Definition

```python
class DeployableTraderAgent(DeployablePredictionAgent):
```

### Key Features
- **Automated Trading:** Places trades based on market conditions and probabilistic analysis.
- **Market Verification:** Ensures markets meet specified criteria before executing trades.
- **Customizable Trading Strategy:** Subclasses can override methods to implement custom betting logic.
- **Support for Multiple Market Types:** Compatible with `OMEN`, `MANIFOLD`, and `POLYMARKET`.
- **Integrated Logging and Monitoring:** Utilizes Langfuse for performance tracking.

## Initialization Parameters

| Parameter          | Type     | Default                         | Description |
|-------------------|---------|--------------------------------|-------------|
| `enable_langfuse` | `bool`  | `APIKeys().default_enable_langfuse` | Enables Langfuse monitoring. |
| `store_predictions` | `bool`  | `True`                          | Stores market predictions. |
| `store_trades`     | `bool`  | `True`                          | Stores trade data. |
| `place_trades`     | `bool`  | `True`                          | Determines whether trades should be executed. |

## Methods

### `run(self, market_type: MarketType) -> None`
Runs the trading agent for a given market type. This method is typically overridden by subclasses.

### `initialize_langfuse(self) -> None`
Initializes Langfuse monitoring.

### `check_min_required_balance_to_trade(self, market: AgentMarket) -> None`
Checks whether the agent has enough balance to place trades.

### `get_betting_strategy(self, market: AgentMarket) -> BettingStrategy`
Defines the betting strategy to use when placing trades. 

### `build_trades(self, market: AgentMarket, answer: ProbabilisticAnswer, existing_position: Position | None) -> list[Trade]`
Generates trades based on the given market and prediction data.

### `process_market(self, market_type: MarketType, market: AgentMarket, verify_market: bool = True) -> ProcessedTradedMarket | None`
Processes a given market and places trades accordingly.

### `after_process_market(self, market_type: MarketType, market: AgentMarket, processed_market: ProcessedMarket | None) -> None`
Handles post-processing after a market has been processed.

## Example: Creating a Custom Trading Agent

Below is an example of how to create a custom agent by subclassing `DeployableTraderAgent`.

```python
import typing as t
from datetime import timedelta

from prediction_market_agent_tooling.deploy.agent import DeployableTraderAgent
from prediction_market_agent_tooling.markets.agent_market import AgentMarket
from prediction_market_agent_tooling.markets.data_models import (
    ProbabilisticAnswer,
    Probability,
    Trade,
    TradeType,
    TokenAmount
)
from prediction_market_agent_tooling.markets.markets import MarketType
from prediction_market_agent_tooling.tools.utils import utcnow

class DeployableArbitrageAgent(DeployableTraderAgent):
    """Agent that places mirror bets on Omen for risk-neutral profit."""

    model = "gpt-4o"
    total_trade_amount = TokenAmount(amount=0.1, currency="xDAI")
    bet_on_n_markets_per_run = 5
    n_markets_to_fetch = 50

    def run(self, market_type: MarketType) -> None:
        if market_type != MarketType.OMEN:
            raise RuntimeError("Arbitrage agent only works with Omen.")
        super().run(market_type=market_type)

    def answer_binary_market(self, market: AgentMarket) -> ProbabilisticAnswer | None:
        return ProbabilisticAnswer(p_yes=Probability(0.5), confidence=1.0)

    def build_trades(
        self,
        market: AgentMarket,
        answer: ProbabilisticAnswer,
        existing_position: Position | None,
    ) -> list[Trade]:
        trade = Trade(
            trade_type=TradeType.BUY,
            outcome=answer.p_yes,
            amount=self.total_trade_amount
        )
        return [trade]
```

### Explanation
- **Custom `run` Method:** Ensures the agent only runs for the `OMEN` market.
- **Custom `answer_binary_market` Method:** Provides a fixed probabilistic answer.
- **Custom `build_trades` Method:** Creates a simple buy trade based on market predictions.

## Deployment

### Deploying Locally
```python
agent = DeployableArbitrageAgent()
agent.deploy_local(market_type=MarketType.OMEN, sleep_time=10, run_time=3600)
```

### Deploying to GCP
```python
agent = DeployableArbitrageAgent()
agent.deploy_gcp(
    repository="my-repo",
    market_type=MarketType.OMEN,
    api_keys=APIKeys(),
    memory=512,
    cron_schedule="*/5 * * * *"
)
```


The `DeployableTraderAgent` class provides a robust framework for creating automated trading agents for prediction markets. By subclassing it, developers can implement custom trading strategies tailored to their specific requirements.
