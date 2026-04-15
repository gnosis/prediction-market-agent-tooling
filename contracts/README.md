# Polymarket migration Solidity

Canonical Gnosis Guild [1155-to-20](https://github.com/gnosis/1155-to-20)
`Wrapped1155Factory`, used by `scripts/polymarket_migrate_position.py
--wrap-output` to turn CTF outcome ERC-1155s into per-position ERC-20s that
can trade on CoW, Uniswap, Balancer, etc.

## Deployed address

- Polygon mainnet: `0x60106ef4e33C56becf54D2FFbE55139418d4aAAE`
  (see `prediction_market_agent_tooling/markets/polymarket/constants.py`)
- Deployed via `forge create` from this project's operator EOA.

## Setup

```bash
cd contracts
forge install OpenZeppelin/openzeppelin-contracts@v3.4.2 --shallow --no-git
forge build
```

`lib/`, `out/`, `cache/`, and `broadcast/` are `.gitignore`d — rerun
`forge install` + `forge build` after a fresh clone.

## Deploy (one-time, already done)

```bash
forge create src/Wrapped1155Factory.sol:Wrapped1155Factory \
    --rpc-url "$POLYGON_RPC_URL" \
    --private-key "$BET_FROM_PRIVATE_KEY" \
    --broadcast
```
