# CoW Protocol Cross-Chain Bridge Service

Node.js service wrapping `@cowprotocol/sdk-bridging` for Python consumption.

## Status

⚠️ **Placeholder Implementation** — The TypeScript bridge logic is scaffolded but not yet integrated with the actual CoW SDK. Full integration requires 3-4 hours of work following CoW Protocol's official examples.

## What's Implemented

- ✅ CLI interface and argument parsing
- ✅ Input validation (addresses, chain IDs, amounts)
- ✅ JSON output format for Python consumption
- ✅ Error handling structure
- ⏸️ Actual CoW SDK integration (requires `@cowprotocol/sdk-bridging` setup)

## Setup

```bash
cd services/cow-bridge
npm install
npm run build
```

## Usage

### CLI

```bash
./dist/bridge.js \
  --sellToken 0xEeeeeEeeeEeEeeEeEeEeeEEEeeeeEeeeeeeeEEeE \
  --buyToken 0x2791Bca1f2de4661ED88A30C99A7a9449Aa84174 \
  --amount 1000000000000000000 \
  --privateKey 0x...
```

### From Python

```python
import subprocess
import json

result = subprocess.run(
    ['node', 'services/cow-bridge/dist/bridge.js',
     '--sellToken', '0xEeee...',
     '--buyToken', '0x2791...',
     '--amount', '1000000000000000000',
     '--privateKey', private_key],
    capture_output=True,
    text=True,
    timeout=180
)

response = json.loads(result.stdout)
if response['success']:
    print(f"Bridge successful: {response['txHash']}")
else:
    print(f"Bridge failed: {response['error']}")
```

## Environment Variables

```bash
GNOSIS_RPC_URL=https://rpc.gnosischain.com
POLYGON_RPC_URL=https://polygon-rpc.com
```

## Response Format

```json
{
  "success": true,
  "txHash": "0x...",
  "estimatedTime": 120
}
```

Or on error:

```json
{
  "success": false,
  "error": "Error message"
}
```

## TODO: CoW SDK Integration

The actual bridge implementation requires:

1. **Install CoW SDK:**
   ```bash
   npm install @cowprotocol/sdk-bridging
   ```

2. **Initialize BridgingSdk:**
   ```typescript
   import { BridgingSdk } from '@cowprotocol/sdk-bridging';
   
   const sdk = new BridgingSdk({
     chainId: 100,
     signer: wallet
   });
   ```

3. **Create bridge order with hooks:**
   - CowShed account proxy setup
   - Signed post-settlement hooks
   - AppData construction with bridge metadata

4. **Submit order to CoW API:**
   ```typescript
   const order = await sdk.createBridgeOrder({
     sellToken,
     buyToken,
     sellAmount: amount,
     destinationChainId: 137
   });
   ```

5. **Poll for settlement:**
   - Wait for CoW order to settle on Gnosis
   - Hook triggers bridge provider (Bungee)
   - Poll destination chain for arrival
   - Return destination tx hash

## References

- [CoW Protocol SDK](https://github.com/cowprotocol/cow-sdk)
- [CoW Swap UI (reference implementation)](https://github.com/cowprotocol/cowswap)
- [Bungee Bridge API](https://docs.socket.tech/)

## Testing

Once implemented, test with:

```bash
# Test with $1 xDAI → POL
npm run dev -- \
  --sellToken 0xEeeeeEeeeEeEeeEeEeEeeEEEeeeeEeeeeeeeEEeE \
  --buyToken 0x0d500B1d8E8eF31E21C99d1Db9A6444d3ADf1270 \
  --amount 1000000000000000000 \
  --privateKey $TEST_PRIVATE_KEY
```
