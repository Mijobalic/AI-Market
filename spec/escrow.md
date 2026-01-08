# AI-Market Escrow & Payment System

## Overview

Trustless payment flow for the inference marketplace.

---

## Payment Flow

```
┌────────────────────────────────────────────────────────────────┐
│                    ESCROW FLOW                                  │
├────────────────────────────────────────────────────────────────┤
│                                                                 │
│  1. REQUEST          2. ESCROW           3. WORK               │
│  ┌──────────┐        ┌──────────┐        ┌──────────┐          │
│  │ Requester│───────▶│  Lock    │───────▶│  Bidder  │          │
│  │ posts job│        │  max_price│       │  executes│          │
│  └──────────┘        │  in escrow│       └──────────┘          │
│       │              └──────────┘              │                │
│       │                    │                   │                │
│       │              4. RESULT               ▼                │
│       │              ┌──────────┐        ┌──────────┐          │
│       │              │  Validate│◀───────│  Submit  │          │
│       │              │  or      │        │  result  │          │
│       │              │  dispute │        └──────────┘          │
│       │              └──────────┘                              │
│       │                    │                                   │
│       │              5. RELEASE                                │
│       │              ┌──────────┐                              │
│       └─────────────▶│  Pay     │                              │
│        (approve)     │  bidder  │                              │
│                      └──────────┘                              │
│                                                                │
└────────────────────────────────────────────────────────────────┘
```

---

## Escrow States

| State | Description | Timeout Action |
|-------|-------------|----------------|
| `CREATED` | Request posted, escrow locked | Cancel after 1h if no bids |
| `ASSIGNED` | Winner selected, working | Refund if no result in 10min |
| `SUBMITTED` | Result submitted, awaiting validation | Auto-approve after 1h |
| `APPROVED` | Requester approved, payment released | — |
| `DISPUTED` | Quality challenge raised | Validator decides |
| `REFUNDED` | Cancelled or failed, funds returned | — |

---

## Escrow Contract (Conceptual)

```python
class Escrow:
    request_id: str
    requester: str      # Wallet address
    bidder: str         # Winner's wallet
    amount: float       # ANT locked
    state: EscrowState
    
    created_at: datetime
    assigned_at: datetime
    submitted_at: datetime
    resolved_at: datetime
    
    result_hash: str    # Hash of submitted result
    validator: str      # If dispute, who resolves
```

---

## Fee Structure

| Party | Fee | Notes |
|-------|-----|-------|
| **Bidder** | 100% - platform fee | Gets paid for work |
| **Platform** | 2-5% | Covers infrastructure |
| **Validator** | 1% (on disputes only) | Incentive to validate |

---

## Dispute Resolution

**When requester challenges quality:**

1. **Dispute raised** (within 1h of submission)
2. **Validator selected** (random from validator pool)
3. **Validator reviews** (prompt + response)
4. **Decision:**
   - **Valid** → Bidder gets 100%, requester pays dispute fee
   - **Invalid** → Requester refunded, bidder slashed

**Validator incentives:**
- Correct decisions → Small fee + reputation up
- Incorrect (appealed) → Reputation down + stake slashed

---

## Implementation Phases

### Phase 1: Local Simulation (Current)
- File-based escrow state
- Requester always approves
- No real tokens

### Phase 2: On-Chain Escrow
- Smart contract on Arbitrum
- Real ANT token locking
- Timeout-based auto-resolution

### Phase 3: Full Marketplace
- Validator network
- Reputation staking
- Cross-chain support

---

## Local Simulator Design

```python
class LocalEscrow:
    """File-based escrow for testing."""
    
    def create(request_id, requester, max_price):
        """Lock funds in escrow."""
        
    def assign(request_id, bidder, bid_price):
        """Winner selected, work begins."""
        
    def submit(request_id, result_hash):
        """Result submitted, awaiting validation."""
        
    def approve(request_id):
        """Requester approves, release funds."""
        
    def dispute(request_id, reason):
        """Requester challenges quality."""
        
    def resolve(request_id, decision):
        """Validator resolves dispute."""
        
    def refund(request_id):
        """Cancel and return funds."""
```

---

## Integration with Autonomi

- **Escrow state** → Scratchpad (mutable)
- **Escrow history** → Immutable chunks
- **Dispute evidence** → Immutable storage
- **Validator selection** → On-chain randomness

---

## Security Considerations

1. **Double-spend protection** — Escrow locks immediately
2. **Timeout safety** — Auto-resolution prevents lockups
3. **Sybil resistance** — Reputation + staking required
4. **Privacy** — Optional encrypted prompts

---

*Next: Implement LocalEscrow class in prototype*
