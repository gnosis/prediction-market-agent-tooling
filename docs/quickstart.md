# Gnosis Agent Quickstart Guide

## Overview
Gnosis Agent is a library for exploring AI Agent frameworks using a prediction market betting agent as an example. These agents interact with markets from **Manifold, Presagio, and Polymarket**.

This is built on top of the prediction market APIs from the [Gnosis Prediction Market Agent Tooling](https://github.com/gnosis/prediction-market-agent-tooling).

## Setup

1. **Clone the repository:**
   ```bash
   git clone https://github.com/gnosis/prediction-market-agent.git
   cd prediction-market-agent
   ```
2. **Install dependencies using poetry:**
   ```bash
   python3.10 -m pip install poetry
   python3.10 -m poetry install
   ```
3. **Activate the virtual environment:**
   ```bash
   python3.10 -m poetry shell
   ```

### Environment Variables
Create a `.env` file in the root of the repository and add the following variables:


    Please Note: Requirements for env variables may differ based upon which agent you want to run. Always check the agent file to verify the variables required.

```ini
MANIFOLD_API_KEY=your_manifold_api_key
BET_FROM_PRIVATE_KEY=your_private_key
OPENAI_API_KEY=your_openai_api_key
```

For additional variables, check `.env.example` in the repository.

## Running the Agents
To execute an agent, run the following command:

```bash
python prediction_market_agent/run_agent.py <AGENT> <MARKET_TYPE>
```

### Available Agents
Replace `<AGENT>` with one of the following:
- `coinflip`
- `replicate_to_omen`
- `think_thoroughly`
- `think_thoroughly_prophet`
- `knownoutcome`
- `microchain`
- `metaculus_bot_tournament_agent`
- `prophet_gpt4o`
- `social_media`
- `omen_cleaner`

For a full list, run:
```bash
python prediction_market_agent/run_agent.py --help
```

### Available Market Types
Replace `<MARKET_TYPE>` with one of:
- `omen`
- `manifold`
- `polymarket`
- `metaculus`

## Interactive Streamlit Apps
The project includes **Streamlit apps** for interactive agent interactions:

1. **Autonomous agent with function calling:**
   ```bash
   streamlit run prediction_market_agent/agents/microchain_agent/app.py
   ```

2. **Prediction market research and betting:**
   ```bash
   streamlit run scripts/agent_app.py
   ```



## Deploying Your Own Agent
1. Subclass the `DeployableTraderAgent`.
2. Check `DeployableCoinFlipAgent` for a minimal example.
3. Add your agent to the `RUNNABLE_AGENTS` dictionary in `prediction_market_agent/run_agent.py`.
4. Use it as an entry point for cloud deployment.


