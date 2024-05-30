# Prediction Market Agent Tooling

Tooling for benchmarking, deploying and monitoring agents for prediction market applications.

## Setup

Install the project dependencies with `poetry`, using Python >=3.10:

```bash
python3.10 -m pip install poetry
python3.10 -m poetry install
python3.10 -m poetry shell
```

Create a `.env` file in the root of the repo with the following variables:

Deploying and monitoring agents using GCP requires that you set up the gcloud CLI (see [here](https://cloud.google.com/sdk/docs/install) for installation instructions, and use `gcloud auth login` to authorize.)

```bash
MANIFOLD_API_KEY=...
BET_FROM_PRIVATE_KEY=...
OPENAI_API_KEY=...
```

## Benchmarking

Create a benchmarkable agent by subclassing the `AbstractBenchmarkedAgent` base class, and plug in your agent's research and prediction functions into the `predict` method.

Use the `Benchmarker` class to compare your agent's predictions vs. the 'wisdom of the crowd' on a set of markets from your chosen prediction market platform.

For example:

```python
import prediction_market_agent_tooling.benchmark.benchmark as bm
from prediction_market_agent_tooling.benchmark.agents import RandomAgent
from prediction_market_agent_tooling.markets.markets import MarketType, get_binary_markets

benchmarker = bm.Benchmarker(
    markets=get_binary_markets(limit=10, market_type=MarketType.MANIFOLD),
    agents=[RandomAgent(agent_name="a_random_agent")],
)
benchmarker.run_agents()
md = benchmarker.generate_markdown_report()
```

This produces a markdown report that you can use for comparing agents side-by-side, like:

![Benchmark results](assets/comparison-report.png)

## Deploying

> **Deprecated**: We suggest using your own infrastructure to deploy, but you may still find this useful.

Create a deployable agent by subclassing the `DeployableTraderAgent` base class, and implementing the `answer_binary_market` method.

For example, deploy an agent that randomly picks an outcome:

```python
import random
from prediction_market_agent_tooling.deploy.agent import DeployableTraderAgent
from prediction_market_agent_tooling.markets.agent_market import AgentMarket

class DeployableCoinFlipAgent(DeployableTraderAgent):
    def answer_binary_market(self, market: AgentMarket) -> bool | None:
        return random.choice([True, False])

DeployableCoinFlipAgent().deploy_gcp(...)
```

### Safe

Agents can control funds via a wallet primary key only, or optionally via a [Safe](https://safe.global/) as well. For deploying a Safe manually for a given agent, run the script below:

```commandline
poetry run python scripts/create_safe_for_agent.py  --from-private-key <YOUR_AGENT_PRIVATE_KEY> --salt-nonce 42
```

This will output the newly created Safe in the terminal, and it can then be copied over to the deployment part (e.g. Terraform).
Note that `salt_nonce` can be passed so that the created safe is deterministically created for each agent, so that, if the same `salt_nonce` is used, the script will not create a new Safe for the agent, instead it will output the previously existent Safe.

You can then specify this agent's Safe address with the `SAFE_ADDRESS` environment variable.

## Monitoring

Monitor the performance of the agents deployed to GCP, as well as meta-metrics of the prediction market platforms they are deployed to.

This runs as a streamlit app on a localhost server, executed with:

```bash
PYTHONPATH=. streamlit run examples/monitor/monitor.py
```

Which launches in the browser:

![Monitoring](assets/monitoring.png)

## The Market Platforms

The following prediction market platforms are supported:

| Platform                              | Benchmarking | Deployment | Monitoring |
|---------------------------------------|--------------|------------|------------|
| [Manifold](https://manifold.markets/) | ✅ | ✅ | ✅ |
| [AIOmen](https://aiomen.eth.limo/)    | ✅ | ✅ | ✅ |
| [Polymarket](https://polymarket.com/) | ✅ | ❌ | ❌ |

## Prediction Markets Python API

We have built clean abstractions for taking actions on the different prediction market platforms (retrieving markets, buying and selling tokens, etc.). This is currently undocumented, but for now, inspecting the [`AgentMarket`](https://github.com/gnosis/prediction-market-agent-tooling/blob/1e497fff9f2b53e4e3e1beb5dda08b4d49da881b/prediction_market_agent_tooling/markets/agent_market.py) class and its methods is your best bet.

For example:

```python
from prediction_market_agent_tooling.config import APIKeys
from prediction_market_agent_tooling.markets.agent_market import SortBy
from prediction_market_agent_tooling.markets.omen.omen import OmenAgentMarket

# Place a bet on the market closing soonest
market = OmenAgentMarket.get_binary_markets(limit=1, sort_by=SortBy.CLOSING_SOONEST)[0]
market.place_bet(outcome=True, amount=market.get_bet_amount(0.1))

# View your positions
my_positions = OmenAgentMarket.get_positions(user_id=APIKeys().bet_from_address)
print(my_positions)

# Sell position (accounting for fees)
market.sell_tokens(outcome=True, amount=market.get_bet_amount(0.095))
```

This API can be built on top of to create your application. See [here](https://github.com/gnosis/prediction-market-agent/tree/main/prediction_market_agent/agents/microchain_agent) for an example.

## Contributing

See the [Issues](https://github.com/gnosis/prediction-market-agent-tooling/issues) for ideas of things that need fixing or implementing. The team is also receptive to new issues and PRs.

We use `mypy` for static type checking, and `isort`, `black` and `autoflake` for linting. These all run as steps in CI.
