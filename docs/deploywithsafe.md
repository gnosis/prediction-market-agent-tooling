# Deploy your Prediction Market Agent with Safe

Prediction Market Agent Tooling (PMAT) includes in-built Safe integration, allowing users to deploy and fund a Safe wallet. This wallet is used to place bets on different prediction markets securely and efficiently. By leveraging Safe wallets, users can enhance the security and transparency of their prediction market interactions.

## Benefits of using a Safe Wallet
- Multiple owner configuration: Enables multi-signature control for enhanced security.

- Batching transactions: Allows executing multiple transactions in a single batch, reducing gas costs and improving efficiency.

- Leveraging transaction sponsorships through Safe Modules: Enables external funding or fee payment by sponsors.

## Steps to integerate Safe Wallet with PMAT

1. Install poetry if not already isntalled
```
python3.10 -m pip install poetry
python3.10 -m poetry install
python3.10 -m poetry shell
```

2. Deploy a Safe using an EOA

Make sure that the EOA has enough balance in xDAI for the transaction to go through.

```
poetry run python scripts/create_safe_for_agent.py  --from-private-key <YOUR_AGENT_PRIVATE_KEY> 
```

### Configuration Options

| Option               | Type    | Default  | Description |
|----------------------|---------|----------|-------------|
| `--from-private-key` | String  | Required | The private key of the agent deploying the Safe |
| `--rpc-url`         | String  | Optional     | Custom RPC URL for deployment  |
| `--salt-nonce`      | Integer | Optional   | Salt nonce for deterministic Safe deployment |
| `--fund-safe`       | Flag    | Optional  | Whether to fund the Safe upon creation |
| `--fund-amount-xdai` | Integer | Optional (Default: 1)        | Amount of xDAI to fund the Safe with (if `--fund-safe` is enabled) |

3. The abover step will print the Safe wallet address. Put that address in the **SAFE_ADDRESS** env variable. Also make sure to put the Safe's owners private key in the **BET_FROM_PRIVATE_KEY** env variable.


 If the above two *env* varibles are configured correctly, all agents by default will start using the Safe address to transact and place bets on the prediction markets. 
 
 Always make sure to have enough balace in your safe wallet for your agent to transact seamlessly.