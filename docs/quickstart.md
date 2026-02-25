# Quickstart Guide

This is a quickstart guide to help you get started with your first prediction market agent using the PMAT library on Gnosis Chain.

### 1. Dependencies
Install all the necessary dependencies mentioned in the [Dependencies](dependencies.md) page.

### 2. Create your project

Create a new project directory

```
mkdir basic-prediction-market-agent
cd basic-prediction-market-agent
```
Set up a virtual environment

```
python -m venv venv
source venv/bin/activate  
# On Windows use `venv\Scripts\activate`
```
Create a requirements.txt file yet and add the following dependencies:

```
prediction-market-agent-tooling[langchain]
python-dotenv
pydantic
```

Install the libraries

```
python -m pip install -r requirements.txt
```
### 3. Configure Environment Variables

Create .env and fill in the required API keys:

```
GRAPH_API_KEY=

OPENAI_API_KEY=

BET_FROM_PRIVATE_KEY= 

# Make sure you have enough xDAI in the wallet you use here.

```

### 4. Create a Basic Prediction Market Agent

Create a new file named **basic_agent.py**

Create a class BasicAgent which inherits from **DeployableTraderAgent** class, meaning it extends the base class for a trading agent in the prediction market framework.

```
import random

from prediction_market_agent_tooling.deploy.agent import DeployableTraderAgent
from prediction_market_agent_tooling.gtypes import Probability
from prediction_market_agent_tooling.markets.agent_market import AgentMarket
from prediction_market_agent_tooling.markets.data_models import ProbabilisticAnswer
from prediction_market_agent_tooling.markets.markets import MarketType


class BasicAgent(DeployableTraderAgent):
    bet_on_n_markets_per_run = 1

    def answer_binary_market(self, market: AgentMarket) -> ProbabilisticAnswer | None:
        decision = random.choice([True, False])
        return ProbabilisticAnswer(
            confidence=0.5,
            p_yes=Probability(float(decision)),
            reasoning="I flipped a coin to decide.",
        )


if __name__ == "__main__":
    agent = BasicAgent()
    agent.run(market_type=MarketType.OMEN)

```

### 5. Run the agent

```
python basic_agent.py
```

Now, you can see the output on your terminal that the agent automatically pulls in a prediction amrket question and bets randomly based upon the probabilistic answer as inpmemented on the above code.

Voilaa!!! You have sucessfully built and deployed a new prediction market agent on Gnosis Mainnet.

From here you can go ahead and customize the script any way you would like, add new functions, more complexity and nuanced decison making, etc.