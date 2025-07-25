# Benchmarker: Evaluating Prediction Market Agents

## Introduction

The `Benchmarker` class is a tool designed to evaluate and compare multiple prediction market agents. It helps measure their ability to make accurate and confident predictions by running agents on a set of predefined markets and analyzing their results using various performance metrics.

## Getting Started

### Instantiating the Benchmarker
```python
benchmarker = Benchmarker(
    markets=markets,
    agents=agents,
    cache_path="predictions.json"
)
```
### Parameters:
- **markets**: A list of `AgentMarket` instances representing different prediction markets.
- **agents**: A list of agents that will participate in the benchmarking process.
- **cache_path** (optional): File path for storing cached predictions.
- **only_cached** (optional, default: False): If `True`, only cached predictions are used.

### Key Features:
- Ensures agents have unique names.
- Filters out markets with unsuccessful resolutions.
- Supports caching to improve efficiency.
- Allows the addition of custom evaluation metrics.

## Methods Overview

### Adding and Retrieving Predictions
#### `add_prediction`  
```python
add_prediction(agent, prediction, market_question)
```
Adds an agent’s prediction for a specific market question.

#### `get_prediction`  
```python
get_prediction(agent_name, question)
```
Retrieves the prediction made by an agent for a given market question.

### Running Agents
#### `run_agents`  
```python
run_agents(enable_timing=True)
```
Executes all registered agents, collecting predictions and storing them in the cache if applicable.

### Analyzing Market Data
#### `compute_metrics`  
```python
compute_metrics()
```
Calculates various metrics that evaluate agent performance.

#### `get_markets_summary`  
```python
get_markets_summary()
```
Provides a summary of each market, including agent predictions.

#### `get_markets_results`  
```python
get_markets_results()
```
Returns overall statistics about the prediction markets, such as resolution proportions.

### Generating Reports
#### `generate_markdown_report`  
```python
generate_markdown_report()
```
Creates a markdown report summarizing market outcomes, agent performances, and computed metrics.

## Metrics Computed

The `Benchmarker` class computes several useful statistics, including:

- **MSE for `p_yes`**: Measures accuracy of probability predictions.
- **Mean confidence**: Average confidence level across all predictions.
- **Prediction accuracy**: Calculates the percentage of correct outcomes.
- **Precision and recall**: Evaluates accuracy of `yes` and `no` predictions.
- **Confidence/error correlation**: Assesses the relationship between prediction confidence and actual error.
- **Mean cost and time**: Computes average computational cost and time per prediction.
- **Proportion of answerable and answered questions**: Analyzes agent responsiveness.

## Example Usage

```python
benchmarker.run_agents()
metrics = benchmarker.compute_metrics()
report = benchmarker.generate_markdown_report()
print(report)
```

This produces a markdown report that you can use for comparing agents side-by-side.