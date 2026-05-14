# Cross-Chain Bridge Implementation Plan

## Issue
#934 — Solve cross-chain swap for Polymarket markets

## Problem
Polymarket agents need USDC.e and POL on Polygon to place bets. Currently, agents must be pre-funded on Polygon. Agents holding xDAI on Gnosis cannot use it without manual bridging.

## Solution Architecture

### 1. Node.js Bridge Service (`services/cow-bridge/`)

**Purpose:** Wrap `@cowprotocol/sdk-bridging` TypeScript SDK for Python consumption.

**Files:**
- `package.json` — dependencies (@cowprotocol/sdk-bridging, express)
- `src/bridge.ts` — main bridge logic
- `src/server.ts` — HTTP server (optional, for subprocess alternative)
- `tsconfig.json` — TypeScript config
- `README.md` — setup and usage docs

**API:**
```typescript
interface BridgeRequest {
  sellToken: string;        // Token address on source chain
  buyToken: string;         // Token address on destination chain
  sellChainId: number;      // Source chain ID (100 = Gnosis)
  buyChainId: number;       // Destination chain ID (137 = Polygon)
  amount: string;           // Amount in wei
  privateKey: string;       // Wallet private key
}

interface BridgeResponse {
  success: boolean;
  txHash?: string;          // Destination chain tx hash
  error?: string;
  estimatedTime?: number;   // Seconds
}
```

**Implementation:**
1. Initialize CowShed account proxy
2. Create bridge order with signed hooks
3. Submit order to CoW Protocol
4. Poll for settlement (30s-2min)
5. Return destination tx hash

### 2. Python Integration (`prediction_market_agent_tooling/tools/tokens/`)

**New file:** `cross_chain_bridge.py`

**Functions:**
```python
def bridge_from_gnosis_to_polygon(
    amount_wei: Wei,
    buy_token: ChecksumAddress,  # USDC.e or WPOL on Polygon
    api_keys: APIKeys,
    timeout: int = 180,  # 3 minutes max wait
) -> str:
    """
    Bridge xDAI from Gnosis to buy_token on Polygon using CoW Protocol.
    
    Returns:
        Destination chain tx hash
    
    Raises:
        ValueError: If bridge fails or times out
    """
    pass

def check_gnosis_balance_and_bridge_if_needed(
    polygon_token: ContractERC20BaseClass,
    required_amount_wei: Wei,
    api_keys: APIKeys,
) -> bool:
    """
    Check if we have enough xDAI on Gnosis to bridge.
    If yes, initiate bridge. If no, return False.
    
    Returns:
        True if bridge was initiated, False if insufficient funds
    """
    pass
```

**Integration point:** Modify `auto_deposit_erc20()` in `auto_deposit.py`

Current flow (line 173-184):
```python
if amount_to_sell_wei > keeping_token.balanceOf(...):
    if isinstance(keeping_token, ContractDepositableWrapperERC20BaseClass):
        auto_deposit_depositable_wrapper_erc20(...)
    else:
        raise ValueError("Not enough of the source token...")
```

New flow:
```python
if amount_to_sell_wei > keeping_token.balanceOf(...):
    if isinstance(keeping_token, ContractDepositableWrapperERC20BaseClass):
        auto_deposit_depositable_wrapper_erc20(...)
    elif chain == Chain.POLYGON:
        # Try cross-chain bridge from Gnosis
        bridged = check_gnosis_balance_and_bridge_if_needed(
            polygon_token=collateral_token_contract,
            required_amount_wei=remaining_to_get_in_collateral_wei,
            api_keys=api_keys,
        )
        if not bridged:
            raise ValueError("Insufficient funds on Polygon and Gnosis")
    else:
        raise ValueError("Not enough of the source token...")
```

### 3. Configuration

**Environment variables** (`.env`):
```bash
# Cross-chain bridge settings
ENABLE_CROSS_CHAIN_BRIDGE=true
BRIDGE_SERVICE_URL=http://localhost:3000  # If using HTTP server
BRIDGE_TIMEOUT_SECONDS=180
BRIDGE_MIN_AMOUNT_USD=1.0  # Don't bridge less than $1
```

**API keys:** Reuse existing `APIKeys.bet_from_private_key` for bridge signing.

### 4. Testing

**Unit tests** (`tests/tools/tokens/test_cross_chain_bridge.py`):
- Mock Node.js service responses
- Test balance checking logic
- Test error handling (timeout, insufficient funds)

**Integration test** (`tests_integration/tools/tokens/test_cross_chain_bridge_live.py`):
- Real $1 xDAI → POL bridge (acceptance criteria)
- Verify destination balance increased
- Measure settlement time

**Test flow:**
1. Fund test wallet with 2 xDAI on Gnosis
2. Call `place_bet()` on Polymarket with empty Polygon wallet
3. Verify auto-bridge triggers
4. Verify bet placement succeeds after bridge completes

### 5. Implementation Steps

**Phase 1: Node.js Service (2-3 hours)**
1. Create `services/cow-bridge/` directory
2. Initialize npm project with TypeScript
3. Install `@cowprotocol/sdk-bridging`
4. Implement bridge logic in `src/bridge.ts`
5. Add CLI interface for testing
6. Document usage in README

**Phase 2: Python Integration (2-3 hours)**
1. Create `cross_chain_bridge.py`
2. Implement subprocess call to Node.js service
3. Add balance checking logic
4. Modify `auto_deposit_erc20()` to call bridge
5. Add logging and error handling

**Phase 3: Testing (2-3 hours)**
1. Write unit tests with mocks
2. Test Node.js service standalone
3. Test Python integration with mocked service
4. Run live integration test with real $1 bridge
5. Verify acceptance criteria

**Phase 4: Documentation (1 hour)**
1. Update main README with cross-chain setup
2. Add troubleshooting section
3. Document environment variables
4. Add example usage

**Total estimated time:** 7-10 hours

### 6. Acceptance Criteria Checklist

- [ ] Node.js service created with `@cowprotocol/sdk-bridging`
- [ ] Python can call the service and wait for bridge completion
- [ ] `place_bet` auto-bridges from xDAI when Polygon funds are insufficient
- [ ] Integration test: real $1 xDAI → POL cross-chain swap
- [ ] Handles bridge settlement time (~30s-2min)

### 7. Edge Cases & Error Handling

**Insufficient xDAI on Gnosis:**
- Check balance before attempting bridge
- Return clear error message with required amount

**Bridge timeout:**
- Default 3-minute timeout
- Log partial progress (order submitted but not settled)
- Allow retry with same order ID

**Bridge failure:**
- Catch CoW SDK errors
- Log full error details
- Suggest manual bridge as fallback

**Minimum bridge amount:**
- CoW internal hooks bypass $30 public API minimum
- But gas costs make <$1 bridges uneconomical
- Enforce $1 minimum in Python layer

**Network issues:**
- Retry logic for RPC calls
- Fallback RPC endpoints
- Clear error messages for connectivity issues

### 8. Alternative Approaches Considered

**Why not pure Python?**
- `@cowprotocol/sdk-bridging` is TypeScript-only
- CowShed account proxy + signed hooks are complex
- AppData construction requires SDK internals
- Reimplementing in Python = high maintenance burden

**Why not HTTP server?**
- Subprocess is simpler for single-user agents
- HTTP adds deployment complexity
- Can add HTTP wrapper later if needed

**Why CoW Protocol over Across/Bungee?**
- Across doesn't support Gnosis chain
- Bungee public API has $30 minimum
- CoW internal hooks bypass minimums
- Already proven in CoW Swap UI

### 9. Future Enhancements

**Multi-chain support:**
- Extend to other chains (Base, Optimism, Arbitrum)
- Generalize bridge logic beyond Gnosis → Polygon

**Bridge provider selection:**
- Allow choosing between Across, Bungee, Near-Intents
- Optimize for speed vs cost

**Batch bridging:**
- Combine multiple small bridges into one
- Reduce gas costs

**Bridge status monitoring:**
- WebSocket updates instead of polling
- Real-time progress notifications

**Automatic rebalancing:**
- Monitor balances across chains
- Proactively bridge before funds run out

## Next Steps

1. Create branch `feat/cross-chain-bridge-934`
2. Implement Phase 1 (Node.js service)
3. Implement Phase 2 (Python integration)
4. Run integration test
5. Submit PR with all acceptance criteria met

## References

- Issue: https://github.com/gnosis/prediction-market-agent-tooling/issues/934
- CoW Protocol SDK: https://github.com/cowprotocol/cow-sdk
- CoW Swap UI (reference): https://swap.cow.fi/
- Bungee API: https://docs.socket.tech/
