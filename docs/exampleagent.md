# Basic Prediction Market Agent Example

This documentation covers two deployable agents used in the **Prediction Market Agent** framework for interacting with prediction markets. These agents extend the `DeployableTraderAgent` class and implement different strategies for answering binary markets.

You can find the full code [here](https://github.com/gnosis/prediction-market-agent/tree/main/prediction_market_agent/agents/coinflip_agent).

## Agents

### 1. DeployableCoinFlipAgent
#### Description
The `DeployableCoinFlipAgent` is a simple agent that makes decisions by flipping a coin. It chooses a binary outcome at random and assigns equal confidence to the decision.

#### Implementation
```python
import random
from prediction_market_agent_tooling.deploy.agent import (
    DeployableTraderAgent,
    ProbabilisticAnswer,
)
from prediction_market_agent_tooling.gtypes import Probability
from prediction_market_agent_tooling.markets.agent_market import AgentMarket
from prediction_market_agent_tooling.markets.markets import MarketType

class DeployableCoinFlipAgent(DeployableTraderAgent):
    def verify_market(self, market_type: MarketType, market: AgentMarket) -> bool:
        return True

    def answer_binary_market(self, market: AgentMarket) -> ProbabilisticAnswer | None:
        decision = random.choice([True, False])
        return ProbabilisticAnswer(
            p_yes=Probability(float(decision)),
            confidence=0.5,
            reasoning="I flipped a coin to decide.",
        )
```


### 2. DeployableAlwaysRaiseAgent
#### Description
The `DeployableAlwaysRaiseAgent` is an agent that immediately raises an exception whenever it is asked to answer a binary market question.

#### Implementation
```python
class DeployableAlwaysRaiseAgent(DeployableTraderAgent):
    def answer_binary_market(self, market: AgentMarket) -> ProbabilisticAnswer | None:
        raise RuntimeError("I always raise!")
```

#### Conclusion

- **`DeployableCoinFlipAgent`** provides a **randomized** decision-making approach.
- **`DeployableAlwaysRaiseAgent`** is designed for **exception handling and debugging**.
- Both agents serve different purposes in testing and deploying prediction market agents.

For more details, refer to the [Prediction Market Agent Tooling](https://github.com/gnosis/prediction-market-agent-tooling).
